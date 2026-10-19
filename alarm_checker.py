# ФАЙЛ: alarm_checker.py | ПРОЄКТ: «Київський не гідрометцентр» | ЗАДАЧА: тривога Київ / відбій
# КУДИ КЛАСТИ: корінь репозиторію   (ПАРА: .github/workflows/alarm_monitor.yml; банери alert_start_banner_1.jpg і alert_end_banner_1.jpg — поруч)
"""Монітор тривог міста Києва для каналу «Київський не гідрометцентр».

Читає веб-превʼю Telegram-каналу-джерела (t.me/s/<канал>) і публікує ТІЛЬКИ зміни статусу міста Києва:
  🔴 Київ — повітряна тривога   (alert_start_banner_1.jpg)
  🟢 Київ — відбій              (alert_end_banner_1.jpg)
Тривога в районах Київської області НЕ породжує нових постів:
  * під час тривоги в Києві пост із початком тривоги РЕДАГУЄТЬСЯ (без звуку) — додається список районів;
  * у пості-відбої є примітка «тривога зберігається в: ...», якщо в області вона ще триває.

Змінні оточення:
  TELEGRAM_BOT_TOKEN, CHAT_ID  - обовʼязкові (секрети GitHub)
  SOURCE_CHANNEL  - імʼя каналу-джерела без @ (за замовчуванням air_alert_ua)
  SOURCE_NAME     - назва джерела для підпису
  LOOP_MINUTES    - скільки хвилин працювати в циклі (0 = одна перевірка і вихід)
  POLL_SECONDS    - пауза між перевірками, за замовчуванням 120
  COMMIT_STATE    - "1": зберігати стан у git одразу після змін
  DRY_RUN         - "1": нічого не надсилати і не зберігати, лише показати, що було б надіслано

Перевірка логіки без мережі:  python alarm_checker.py --selftest
"""
import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# Журнал подій для «Підсумку тижня». Необовʼязковий: якщо events_db.py немає — працюємо без нього.
try:
    from events_db import commit_journal, safe_log
except Exception:
    def safe_log(*args, **kwargs):
        return False

    def commit_journal():
        return None

# --- НАЛАШТУВАННЯ -------------------------------------------------------------
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL", "air_alert_ua")
SOURCE_NAME = os.getenv("SOURCE_NAME", "Повітряна тривога")
CHANNEL_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
CHANNEL_LINK = f"https://t.me/{SOURCE_CHANNEL}"

BANNERS = {"START": "alert_start_banner_1.jpg", "END": "alert_end_banner_1.jpg"}
HASHTAGS = {"START": "#Київ #Тривога", "END": "#Київ #Відбій"}

# райони Київської області (після реформи 2020 року)
KYIV_RAIONS = ["Білоцерківський", "Бориспільський", "Броварський", "Бучанський",
               "Вишгородський", "Обухівський", "Фастівський"]

MAX_AGE_MIN = 60        # пости старше цього віку не публікуємо (лише враховуємо у стані)
MAX_PAGES = 3           # скільки сторінок превʼю підтягувати, якщо за 2 хв накопичилось багато постів

STATE_FILE = "alarm_state.json"
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
LOOP_MINUTES = float(os.getenv("LOOP_MINUTES", "0"))
DRY_RUN = os.getenv("DRY_RUN", "").strip() == "1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

LETTER = "А-Яа-яІіЇїЄєҐґ"
CITY_RE = re.compile(rf"(?<![{LETTER}])(?:Київ|Києві|Києва|Києву)(?![{LETTER}])", re.IGNORECASE)
OBLAST_RE = re.compile(r"київськ\w*\s+област|київщин", re.IGNORECASE)
RAION_RE = re.compile(rf"([{LETTER}]+ий)\s+район", re.IGNORECASE)


# --- СТАН ---------------------------------------------------------------------

def new_state():
    return {"last_id": None, "city": False, "oblast": {"all": False, "raions": []}, "msg": None}


def load_state():
    state = new_state()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state.update(json.load(f))
        except Exception as e:
            print(f"Не вдалося прочитати {STATE_FILE}: {e}")
    return state


def commit_state():
    """В GitHub Actions одразу комітимо стан, щоб не втратити його при зупинці запуску."""
    if os.getenv("COMMIT_STATE") != "1":
        return
    try:
        run = lambda *a: subprocess.run(a, check=False, capture_output=True, text=True)
        run("git", "config", "user.name", "github-actions[bot]")
        run("git", "config", "user.email", "github-actions[bot]@users.noreply.github.com")
        run("git", "add", STATE_FILE)
        if run("git", "diff", "--cached", "--quiet").returncode == 0:
            return
        run("git", "commit", "-m", "Update alarm state")
        if run("git", "push").returncode != 0:
            run("git", "pull", "--rebase")
            run("git", "push")
    except Exception as e:
        print(f"Не вдалося зберегти стан у git: {e}")


def save_state(state):
    if DRY_RUN:
        return
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    commit_state()


# --- РОЗБІР КАНАЛУ ------------------------------------------------------------

def _fetch_page(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for el in soup.find_all("div", class_="tgme_widget_message"):
        m = re.search(r"/(\d+)$", el.get("data-post", ""))
        text_el = el.find("div", class_="tgme_widget_message_text")
        if not m or not text_el:
            continue
        ts = None
        t = el.select_one("a.tgme_widget_message_date time")
        if t and t.get("datetime"):
            try:
                ts = datetime.fromisoformat(t["datetime"])
            except ValueError:
                pass
        posts.append((int(m.group(1)), text_el.get_text(" ", strip=True), ts))
    return posts


def fetch_posts(last_id=None):
    """[(номер поста, текст, час)] за зростанням номера. Якщо нових постів багато — підтягує попередні сторінки."""
    posts = _fetch_page(CHANNEL_URL)
    for _ in range(MAX_PAGES - 1):
        if not posts or last_id is None or min(p[0] for p in posts) <= last_id + 1:
            break
        older = _fetch_page(f"{CHANNEL_URL}?before={min(p[0] for p in posts)}")
        if not older:
            break
        posts = older + posts
    posts = list({p[0]: p for p in posts}.values())
    posts.sort(key=lambda p: p[0])
    return posts


def find_raions(text):
    out = []
    for m in RAION_RE.finditer(text):
        name = m.group(1).capitalize()
        if name in KYIV_RAIONS and name not in out:
            out.append(name)
    return out


def parse_post(num, text, ts):
    """Тип події за ТЕКСТОМ поста. None — пост нас не цікавить (інші області, ракурси БпЛА тощо)."""
    flat = re.sub(r"\s+", " ", text).strip()
    low = flat.lower()
    idx = low.find("досі")
    head, tail = (flat[:idx], flat[idx:]) if idx >= 0 else (flat, "")
    head_low = head.lower()

    if "відбій" in head_low:
        kind = "END"
    elif "тривога" in head_low or "тривогу" in head_low:
        kind = "START"
    else:
        return None

    ev = {
        "num": num, "kind": kind, "ts": ts, "text": flat,
        "city": bool(CITY_RE.search(head)),
        "oblast_all": bool(OBLAST_RE.search(head)),
        "raions": find_raions(head),
        "has_tail": idx >= 0,
        "still_city": bool(CITY_RE.search(tail)),
        "still_oblast_all": bool(OBLAST_RE.search(tail)),
        "still_raions": find_raions(tail),
    }
    if not (ev["city"] or ev["oblast_all"] or ev["raions"]):
        return None
    return ev


def apply_event(state, ev):
    """Повертає новий стан після події (стан-аргумент не змінюється)."""
    city = state["city"]
    ob = {"all": state["oblast"]["all"], "raions": list(state["oblast"]["raions"])}

    if ev["kind"] == "START":
        if ev["city"]:
            city = True
        if ev["oblast_all"]:
            ob["all"] = True
        for r in ev["raions"]:
            if r not in ob["raions"]:
                ob["raions"].append(r)
    else:  # END
        if ev["has_tail"]:
            # «досі триває у: ...» — це повний актуальний список того, що ще під тривогою
            city = ev["still_city"]
            ob = {"all": ev["still_oblast_all"], "raions": list(ev["still_raions"])}
        else:
            if ev["city"]:
                city = False
            if ev["oblast_all"]:
                ob = {"all": False, "raions": []}
            ob["raions"] = [r for r in ob["raions"] if r not in ev["raions"]]

    out = dict(state)
    out["city"], out["oblast"] = city, ob
    return out


# --- ПОВІДОМЛЕННЯ -------------------------------------------------------------

def oblast_text(ob):
    if ob["all"]:
        return "уся область"
    if not ob["raions"]:
        return ""
    names = ", ".join(ob["raions"])
    return f"{names} район" if len(ob["raions"]) == 1 else f"{names} райони"


def build_caption(kind, ob):
    footer = f"🔗 Джерело: <a href='{CHANNEL_LINK}'>{html.escape(SOURCE_NAME)}</a> · {HASHTAGS[kind]}"
    t = oblast_text(ob)
    if kind == "START":
        lines = ["🔴 <b>Київ</b> — повітряна тривога"]
        if t:
            lines.append(f"📍 Київщина: {t}")
    else:
        lines = ["🟢 <b>Київ</b> — відбій повітряної тривоги"]
        if t:
            lines.append(f"⚠️ Зверніть увагу: тривога зберігається в області — {t}")
    lines.append(footer)
    return "\n".join(lines)


def _creds():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_alert(kind, caption):
    """Повертає {'id': message_id, 'photo': bool} або None при невдачі."""
    if DRY_RUN:
        print(f"[DRY RUN] було б надіслано ({kind}):\n{caption}\n")
        return {"id": 0, "photo": False}
    token, chat_id = _creds()
    if not token or not chat_id:
        print("Помилка: секрети TELEGRAM_BOT_TOKEN або CHAT_ID не знайдено!")
        return None

    banner = BANNERS.get(kind)
    for attempt in range(3):
        try:
            photo = bool(banner and os.path.exists(banner))
            if photo:
                with open(banner, "rb") as f:
                    r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                      data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                                      files={"photo": f}, timeout=30)
            else:
                if banner:
                    print(f"Банер {banner} не знайдено, надсилаю текстом.")
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  json={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                        "disable_web_page_preview": True}, timeout=20)
            if r.status_code == 200:
                return {"id": r.json()["result"]["message_id"], "photo": photo}
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            print(f"Помилка надсилання: {r.status_code} {r.text}")
            return None
        except Exception as e:
            print(f"Помилка надсилання (спроба {attempt + 1}): {e}")
            time.sleep(3)
    return None


def edit_alert(msg, caption):
    """Тихо редагує вже опублікований пост (редагування не викликає звук у підписників)."""
    if DRY_RUN:
        print(f"[DRY RUN] було б відредаговано пост {msg['id']}:\n{caption}\n")
        return True
    token, chat_id = _creds()
    if not token or not chat_id:
        return False
    method, key = ("editMessageCaption", "caption") if msg.get("photo") else ("editMessageText", "text")
    body = {"chat_id": chat_id, "message_id": msg["id"], key: caption, "parse_mode": "HTML"}
    if not msg.get("photo"):
        body["disable_web_page_preview"] = True
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=body, timeout=20)
        if r.status_code == 200 or "message is not modified" in r.text:
            return True
        print(f"Не вдалося відредагувати пост: {r.status_code} {r.text}")
    except Exception as e:
        print(f"Помилка редагування: {e}")
    return False


# --- ОДНА ПЕРЕВІРКА -----------------------------------------------------------

def is_stale(ts):
    return bool(ts) and datetime.now(timezone.utc) - ts > timedelta(minutes=MAX_AGE_MIN)


def oblast_sig(ob):
    return "all" if ob["all"] else ",".join(sorted(ob["raions"]))


def process_events(state, events, notify=True):
    """Проганяє події по черзі. Повертає (новий стан, чи все надіслано)."""
    for ev in events:
        new = apply_event(state, ev)
        if new["city"] != state["city"]:                       # змінився статус САМОГО МІСТА
            kind = "START" if new["city"] else "END"
            if notify and not is_stale(ev["ts"]):
                res = send_alert(kind, build_caption(kind, new["oblast"]))
                if not res:
                    return state, False                         # стан не рухаємо — повторимо
                print(f"Надіслано: {kind}")
                time.sleep(1)
                new["msg"] = {**res, "sig": oblast_sig(new["oblast"])} if kind == "START" else None
            else:
                print(f"Пост {ev['num']} застарілий — не публікуємо, лише враховуємо.")
                new["msg"] = None
            if kind == "START":
                safe_log("alert", "Тривога: Київ", key=f"alert-{ev['num']}", when=ev["ts"])
            else:
                safe_log("alert_end", "Відбій: Київ", key=f"alert-end-{ev['num']}", when=ev["ts"])
            commit_journal()
        new["last_id"] = ev["num"]
        state = new
        save_state(state)

    # Тривога в Києві триває, а в області список районів змінився — тихо оновлюємо пост про початок
    msg = state.get("msg")
    if notify and state["city"] and msg and msg.get("sig") != oblast_sig(state["oblast"]):
        if edit_alert(msg, build_caption("START", state["oblast"])):
            state = {**state, "msg": {**msg, "sig": oblast_sig(state["oblast"])}}
            save_state(state)
    return state, True


def poll(state):
    posts = fetch_posts(state.get("last_id"))
    if not posts:
        print("Не вдалося знайти повідомлення на сторінці каналу.")
        return state

    # перший запуск: відновлюємо стан за видимими постами, нічого не публікуючи
    if state.get("last_id") is None:
        state = new_state()
        events = [e for e in (parse_post(*p) for p in posts) if e]
        state, _ = process_events(state, events, notify=False)
        state["last_id"] = posts[-1][0]
        state["msg"] = None
        save_state(state)
        print(f"Ініціалізація: останній пост {state['last_id']}, "
              f"Київ під тривогою: {state['city']}, область: {oblast_text(state['oblast']) or 'ні'}")
        return state

    new_posts = [p for p in posts if p[0] > state["last_id"]]
    if not new_posts:
        return state
    events = [e for e in (parse_post(*p) for p in new_posts) if e]
    state, ok = process_events(state, events)
    if ok and new_posts[-1][0] > state["last_id"]:             # непрофільні пости теж вважаємо опрацьованими
        state["last_id"] = new_posts[-1][0]
        save_state(state)
    return state


def main():
    state = load_state()
    deadline = time.time() + LOOP_MINUTES * 60
    while True:
        try:
            state = poll(state)
        except Exception as e:
            print(f"Помилка перевірки: {e}")
        if LOOP_MINUTES <= 0 or time.time() + POLL_SECONDS > deadline:
            break
        time.sleep(POLL_SECONDS)


# --- САМОПЕРЕВІРКА (без мережі) -----------------------------------------------

def selftest():
    global DRY_RUN
    DRY_RUN = True
    samples = [
        (1, "🔴 м. Київ — повітряна тривога"),
        (2, "🔴 Бучанський район — повітряна тривога"),
        (3, "🔴 Вишгородський район — повітряна тривога"),
        (4, "🔴 Харківська область — повітряна тривога"),             # чужа область — ігноруємо
        (5, "1x БпЛА курсом на Вишгород"),                            # не статус — ігноруємо
        (6, "🟢 м. Київ — відбій повітряної тривоги. Досі триває у: Бучанський район"),
        (7, "🟢 Бучанський район — відбій повітряної тривоги"),
        (8, "🔴 Київська область — повітряна тривога"),
        (9, "🔴 м. Київ — повітряна тривога"),
        (10, "🟢 Київська область — відбій повітряної тривоги"),
        (11, "🟢 м. Київ — відбій повітряної тривоги"),
    ]
    events = [e for e in (parse_post(n, t, None) for n, t in samples) if e]
    print(f"Розпізнано подій: {len(events)} із {len(samples)} постів (очікується 9)\n")
    assert len(events) == 9
    state, ok = process_events(new_state(), events)
    assert ok and not state["city"] and not state["oblast"]["raions"] and not state["oblast"]["all"], state
    print("Самоперевірка пройдена.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    print(f"Перевіряємо свіжі пости в каналі {SOURCE_CHANNEL}...")
    main()
    sys.exit(0)
