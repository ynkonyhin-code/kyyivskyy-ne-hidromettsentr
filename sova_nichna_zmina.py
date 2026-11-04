# -*- coding: utf-8 -*-
"""
«Сова-чергова» — нічна зміна каналу «Київський не гідрометцентр» (https://t.me/kyyivskyy_ne_hidromettsentr)

Сова заступає о 00:00, до ранку розповідає тихі історії для тих, хто не спить, і о 03:45 здає зміну Котику
(Котик-черговий заступає о 05:00).

Слоти (за Києвом):
  open   00:00  «Сова заступає»  + скільки лишилось до світанку
  c1     01:15  історія №1 (рубрика чергується за датою)
  c2     02:30  історія №2 (інша рубрика)
  close  03:45  «Сова здає зміну» (картинка зі світанком) + час сходу сонця

Усі пости — БЕЗ ЗВУКУ. Workflow стартує за ~20 хв до цілі, скрипт сам визначає слот за поточним часом,
готує пост і ЧЕКАЄ до точної хвилини (GitHub запускає cron із запізненням).
Повторну публікацію того ж слота за ніч блокує файл sova_nichna_zmina_state.json.

Секрети GitHub: TELEGRAM_BOT_TOKEN, CHAT_ID.
Картинки у корені репо: sova_nich.png і sova_svitanok.png (підходять і варіанти *_kvadrat.png; немає — вийде текст).

Приклади:
  python sova_nichna_zmina.py --slot c1 --dry-run               # показати пост слота (для сьогоднішньої ночі)
  python sova_nichna_zmina.py --slot close --date 2026-12-01 --dry-run
  python sova_nichna_zmina.py --slot open --force               # опублікувати негайно
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from itertools import zip_longest
from zoneinfo import ZoneInfo

import requests

import sova_nichna_zmina_data as D

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(HERE, "sova_nichna_zmina_state.json")

SLOTS = [("open", "00:00"), ("c1", "01:15"), ("c2", "02:30"), ("close", "03:45")]
SLOT_TIME = dict(SLOTS)
EARLY_MIN = 25          # запуск раніше ніж за 25 хв до цілі — не наш слот
LATE_MIN = 35           # запізнення до 35 хв ще публікуємо. Має бути < 40: літній/зимовий cron різняться рівно на годину
SILENT = True           # нічні пости — завжди без звуку



def _find_image(*names: str) -> str:
    """Перший існуючий файл зі списку (у корені репо); якщо жодного — шлях до першого імені (скрипт опублікує текстом)."""
    for n in names:
        path = os.path.join(HERE, n)
        if os.path.isfile(path):
            return path
    return os.path.join(HERE, names[0])


IMG_NIGHT = _find_image("sova_nich.png", "sova_nich_kvadrat.png", "sova_nich.jpg")
IMG_DAWN = _find_image("sova_svitanok.png", "sova_svitanok_kvadrat.png", "sova_svitanok.jpg")
BASE_TAGS = "#СоваЧергова #НічнаЗміна #Київ"
EPOCH = date(2026, 1, 1)


# ── Контент ──────────────────────────────────────────────────────────────────────
def build_pool() -> list[tuple[str, str, str]]:
    """Плоский список (рубрика, заголовок, текст): рубрики йдуть по колу, тому сусідні випуски різні."""
    cols = [[(r, t, x) for (t, x) in D.CONTENT[r]] for r in ("creatures", "sleep", "kyiv")]
    return [item for group in zip_longest(*cols) for item in group if item]


POOL = build_pool()


def pick_content(night: date, slot: str) -> tuple[str, str, str]:
    n = (night - EPOCH).days
    return POOL[(2 * n + (0 if slot == "c1" else 1)) % len(POOL)]


def sun_times(night: date) -> tuple[str, datetime]:
    """Час сходу сонця в Києві для цієї ночі: ('HH:MM', datetime). Береться з розрахунків «Щоденного календаря»."""
    import shchodennyy_kalendar as cal
    sr = cal.sun_info(night)["sunrise"]
    hh, mm = map(int, sr.split(":"))
    return sr, datetime(night.year, night.month, night.day, hh, mm, tzinfo=TZ)


def until(a: datetime, b: datetime) -> str:
    mins = max(0, int((b.astimezone(timezone.utc) - a.astimezone(timezone.utc)).total_seconds() // 60))
    h, m = divmod(mins, 60)
    return f"{h} год {m:02d} хв" if h else f"{m} хв"


def target_dt(night: date, slot: str) -> datetime:
    hh, mm = map(int, SLOT_TIME[slot].split(":"))
    return datetime(night.year, night.month, night.day, hh, mm, tzinfo=TZ)


def build_post(night: date, slot: str) -> tuple[str, str | None]:
    """(текст у HTML, шлях до картинки або None)."""
    e = lambda s: html.escape(s, quote=False)
    rnd = random.Random(f"sova-{night}-{slot}")
    sr, sunrise = sun_times(night)
    left = until(target_dt(night, slot), sunrise)

    if slot == "open":
        text = (f"🦉 <b>Сова-чергова заступає на нічну зміну</b>\n\n{e(rnd.choice(D.OPENERS))}\n\n"
                f"🌅 До світанку — {left} (сонце зійде о {sr}).\n{e(rnd.choice(D.OPENER_CLOSE_LINES))}\n\n"
                f"{BASE_TAGS}")
        return text, IMG_NIGHT

    if slot == "close":
        text = (f"🦉 <b>Сова-чергова здає зміну</b>\n\n{e(rnd.choice(D.CLOSERS))}\n\n"
                f"🌅 Сонце зійде о {sr}, тобто через {left}.\n🐾 О 05:00 заступає Котик-черговий.\n\n"
                f"{BASE_TAGS}")
        return text, IMG_DAWN

    rubric, title, body = pick_content(night, slot)
    info = D.RUBRICS[rubric]
    text = (f"🦉 <b>Сова-чергова</b> · {info['label']}\n\n<b>{e(title)}</b>\n{e(body)}\n\n"
            f"🌅 До світанку — {left}.\n\n{BASE_TAGS} {info['tag']}")
    return text, IMG_NIGHT


# ── Час і стан ───────────────────────────────────────────────────────────────────
def pick_slot(now: datetime):
    """Який слот зараз «наш»: (слот, ніч, ціль) — або None. Порівняння в UTC (безпечно на переході на літній/зимовий час)."""
    now_u = now.astimezone(timezone.utc)
    for day in (now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)):
        for slot, _ in SLOTS:
            target = target_dt(day, slot)
            delta = (now_u - target.astimezone(timezone.utc)).total_seconds() / 60
            if -EARLY_MIN <= delta <= LATE_MIN:
                return slot, day, target
    return None


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mark_done(night: date, slot: str) -> None:
    st = load_state()
    if st.get("date") != night.isoformat():
        st = {"date": night.isoformat(), "done": []}
    if slot not in st["done"]:
        st["done"].append(slot)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def is_done(night: date, slot: str) -> bool:
    st = load_state()
    return st.get("date") == night.isoformat() and slot in st.get("done", [])


# ── Telegram ─────────────────────────────────────────────────────────────────────
def _post(token: str, method: str, **kw):
    for attempt in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=30, **kw)
            if r.status_code == 200:
                return
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            raise RuntimeError(f"{method}: {r.status_code} {r.text[:200]}")
        except requests.RequestException as exc:
            if attempt == 2:
                raise RuntimeError(f"{method}: {exc}")
            time.sleep(3)
    raise RuntimeError(f"{method}: не вдалося після 3 спроб")


def send(token: str, chat: str, text: str, image: str | None) -> None:
    quiet = "true" if SILENT else "false"
    if image and os.path.isfile(image):
        try:
            with open(image, "rb") as fh:
                _post(token, "sendPhoto", data={"chat_id": chat, "caption": text, "parse_mode": "HTML",
                                                "disable_notification": quiet}, files={"photo": fh})
            return
        except Exception as exc:
            print(f"⚠️ Фото не надіслано ({exc}) — публікую текстом.", file=sys.stderr)
    elif image:
        print(f"⚠️ Немає картинки {os.path.basename(image)} — публікую текстом.", file=sys.stderr)
    _post(token, "sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                      "disable_web_page_preview": "true", "disable_notification": quiet})


# ── MAIN ─────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Сова-чергова: нічна зміна каналу «Київський не гідрометцентр»")
    ap.add_argument("--slot", choices=[s for s, _ in SLOTS] + ["auto"], default="auto")
    ap.add_argument("--date", help="РРРР-ММ-ДД ночі (дата, на яку припадає 00:00); за замовчуванням — за поточним часом")
    ap.add_argument("--dry-run", action="store_true", help="не публікувати, лише показати")
    ap.add_argument("--force", action="store_true", help="публікувати негайно, без вікна часу і перевірки «вже опубліковано»")
    args = ap.parse_args()

    now = datetime.now(TZ)
    scheduled = os.getenv("GITHUB_EVENT_NAME") == "schedule" and not args.force and not args.dry_run
    target = None

    if args.slot == "auto" or scheduled:
        found = pick_slot(now)
        if not found:
            print(f"Зараз {now:%H:%M} за Києвом — поза вікнами слотів Сови. Пропускаю цей запуск.")
            return 0
        slot, night, target = found
        if args.slot != "auto" and args.slot != slot:
            print(f"Зараз слот «{slot}», а не «{args.slot}» — вихід.")
            return 0
    else:
        slot = args.slot
        try:
            night = date.fromisoformat(args.date) if args.date else now.date()
        except ValueError:
            ap.error("Неправильна дата. Формат: РРРР-ММ-ДД.")

    if scheduled and is_done(night, slot):
        print(f"Слот «{slot}» за {night} уже опубліковано — вихід.")
        return 0

    text, image = build_post(night, slot)

    if args.dry_run:
        print(f"[слот {slot} · ніч {night} · ціль {SLOT_TIME[slot]} · картинка {os.path.basename(image) if image else '—'}"
              f"{'' if image and os.path.isfile(image) else ' (файлу немає)'}]\n")
        print(text)
        print(f"\n— довжина: {len(text)} символів")
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("❌ Не задано секрети TELEGRAM_BOT_TOKEN і CHAT_ID.", file=sys.stderr)
        return 1

    if scheduled and target:
        wait = (target.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        if 0 < wait <= EARLY_MIN * 60:
            print(f"Усе готово. Чекаємо {int(wait // 60)} хв {int(wait % 60)} с до {SLOT_TIME[slot]} за Києвом…")
            time.sleep(wait)

    send(token, chat, text, image)
    if scheduled or not args.date:          # ручний запуск з --date (чужа ніч) стан не чіпає
        mark_done(night, slot)
    print(f"✅ Опубліковано слот «{slot}» (ніч {night})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
