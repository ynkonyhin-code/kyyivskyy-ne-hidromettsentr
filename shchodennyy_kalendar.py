# -*- coding: utf-8 -*-
"""
Щоденний календар для Telegram-каналу «Київський не гідрометцентр»
https://t.me/kyyivskyy_ne_hidromettsentr

Що робить:
  • збирає дані на дату (свята, церковний календар, іменини, легенда, прикмета);
  • рахує фазу Місяця (алгоритм Меєра) та схід/захід Сонця (формули NOAA) для Києва — без зовнішніх API;
  • малює картку 1280×720 (shchodennyy_kalendar_card.py) і публікує ОДНЕ повідомлення: фото + текст у підписі.

Час публікації: POST_AT (за Києвом). Workflow стартує за ~20 хв до цілі, скрипт готує пост
і ЧЕКАЄ до потрібної хвилини (GitHub запускає cron із запізненням) — так само працює Котик-черговий.
Повторна публікація за ту саму добу блокується файлом shchodennyy_kalendar_state.json.

Секрети GitHub: TELEGRAM_BOT_TOKEN, CHAT_ID (для сумісності також BOT_TOKEN, TELEGRAM_CHAT_ID).

Приклади запуску:
  python shchodennyy_kalendar.py --dry-run                  # лише показати пост і зробити картку
  python shchodennyy_kalendar.py --date 2026-12-25 --dry-run
  python shchodennyy_kalendar.py --force                    # опублікувати негайно
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import shchodennyy_kalendar_data as D

# ── Налаштування ─────────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "shchodennyy_kalendar_state.json")

POST_AT = "07:50"        # час публікації за Києвом (змінюйте тут І в cron у workflow — див. коментар у .yml)
EARLY_MIN = 60           # запуск раніше ніж за 60 хв до цілі — не наш (відсікає зайвий сезонний cron)
LATE_MIN = 120           # запізнення до 120 хв (до 09:50) ще публікуємо — на випадок затримки GitHub
SILENT = False           # True — публікувати без звуку

CITY_LAT, CITY_LON = 50.4501, 30.5234
CHANNEL_NAME = "Київський не гідрометцентр"
CHANNEL_URL = "https://t.me/kyyivskyy_ne_hidromettsentr"
BASE_TAGS = ["Календар", "ЩоденнийКалендар", "КиївськийНеГідрометцентр", "Київ", "Київщина"]

MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня",
              "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
MONTH_TAG = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
             "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
WEEKDAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]


# ═════════════════════════════════════════════════════════════════════════════
#  РУХОМІ СВЯТА
# ═════════════════════════════════════════════════════════════════════════════
def orthodox_easter(year: int) -> date:
    """Великдень за юліанською пасхалією (дата у григоріанському календарі)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return date(year, month, day) + timedelta(days=13)      # 1900–2099


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-й заданий день тижня місяця (n=-1 — останній). weekday: 0=пн … 6=нд."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def moveable_events(d: date) -> tuple[list[str], list[str]]:
    """Повертає (державні/народні, церковні) рядки для рухомих свят."""
    state, church = [], []
    easter = orthodox_easter(d.year)
    off = (d - easter).days

    fixed_church = {
        -49: "Прощена неділя. Завершення Масляної, початок Великого посту|Масляна",
        -48: "Чистий понеділок — початок Великого посту|Великий_піст",
        -7: "Вербна неділя|Вербна_неділя",
        -3: "Чистий четвер|Великий_тиждень",
        -2: "Страсна п'ятниця|Великий_тиждень",
        -1: "Страсна субота|Великий_тиждень",
        0: "Великдень — Воскресіння Христове ✝️|Великдень",
        1: "Великодній понеділок (Поливаний)|Великдень",
        7: "Томина неділя (Антипасха)",
        9: "Радониця — день поминання предків|Радониця",
        39: "Вознесіння Господнє|Вознесіння",
        49: "Трійця — Зелені свята 🌿|Трійця",
        50: "Духів день|Трійця",
    }
    if off in fixed_church:
        church.append(fixed_church[off])
    elif -55 <= off <= -50:
        church.append("Масляний (сирний) тиждень|Масляна")
    elif -47 <= off <= -8:
        church.append("Триває Великий піст|Великий_піст")

    moves = {
        nth_weekday(d.year, 5, 6, 2): "День матері|День_матері",
        nth_weekday(d.year, 5, 3, 3): "День вишиванки 🇺🇦|День_вишиванки",
        nth_weekday(d.year, 5, 6, -1): "День Києва|День_Києва",
        nth_weekday(d.year, 6, 6, 3): "День батька / День медичного працівника|День_батька",
        nth_weekday(d.year, 7, 6, 1): "День Військово-Морських Сил ЗСУ|ВМС",
        nth_weekday(d.year, 8, 6, 1): "День Повітряних Сил ЗСУ|Повітряні_сили",
        nth_weekday(d.year, 11, 5, 4): "День пам'яті жертв голодоморів 🕯|Голодомор",
        nth_weekday(d.year, 10, 6, 1): "День працівників освіти (в Україні — перша неділя жовтня)",
    }
    if d in moves:
        state.append(moves[d])
    return state, church


# ═════════════════════════════════════════════════════════════════════════════
#  МІСЯЦЬ (фази за Меєром, точність ~кілька хвилин) — без зовнішніх залежностей
# ═════════════════════════════════════════════════════════════════════════════
JD_UNIX_EPOCH = 2440587.5
SYNODIC = 29.530588861


def _jd_to_dt(jd: float) -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=jd - JD_UNIX_EPOCH)


def _dt_to_jd(dt: datetime) -> float:
    return dt.timestamp() / 86400 + JD_UNIX_EPOCH


def _phase_jde(k: float) -> float:
    """JDE фази: k цілий — молодик, +0.25 — перша чверть, +0.5 — повня, +0.75 — остання чверть."""
    r = math.radians
    T = k / 1236.85
    jde = (2451550.09766 + SYNODIC * k + 0.00015437 * T**2
           - 0.000000150 * T**3 + 0.00000000073 * T**4)
    E = 1 - 0.002516 * T - 0.0000074 * T**2
    M = r(2.5534 + 29.10535670 * k - 0.0000014 * T**2)
    Mp = r(201.5643 + 385.81693528 * k + 0.0107582 * T**2)
    F = r(160.7108 + 390.67050284 * k - 0.0016118 * T**2)
    Om = r(124.7746 - 1.56375588 * k + 0.0020672 * T**2)
    s = math.sin
    frac = round(k % 1, 2)
    if frac in (0.0, 0.5):
        if frac == 0.0:
            c = (-0.40720, 0.17241, 0.01608, 0.01039, 0.00739, -0.00514, 0.00208)
        else:
            c = (-0.40614, 0.17302, 0.01614, 0.01043, 0.00734, -0.00515, 0.00209)
        corr = (c[0] * s(Mp) + c[1] * E * s(M) + c[2] * s(2 * Mp) + c[3] * s(2 * F)
                + c[4] * E * s(Mp - M) + c[5] * E * s(Mp + M) + c[6] * E**2 * s(2 * M)
                - 0.00111 * s(Mp - 2 * F) - 0.00057 * s(Mp + 2 * F)
                + 0.00056 * E * s(2 * Mp + M) - 0.00042 * s(3 * Mp)
                + 0.00042 * E * s(M + 2 * F) + 0.00038 * E * s(M - 2 * F)
                - 0.00024 * E * s(2 * Mp - M) - 0.00017 * s(Om))
    else:
        corr = (-0.62801 * s(Mp) + 0.17172 * E * s(M) - 0.01183 * E * s(Mp + M)
                + 0.00862 * s(2 * Mp) + 0.00804 * s(2 * F) + 0.00454 * E * s(Mp - M)
                + 0.00204 * E**2 * s(2 * M) - 0.00180 * s(Mp - 2 * F)
                - 0.00070 * s(Mp + 2 * F) - 0.00040 * s(3 * Mp)
                - 0.00034 * E * s(2 * Mp - M) + 0.00032 * E * s(M + 2 * F)
                + 0.00032 * E * s(M - 2 * F) - 0.00028 * E**2 * s(Mp + 2 * M)
                + 0.00027 * E * s(2 * Mp + M) - 0.00017 * s(Om))
        w = (0.00306 - 0.00038 * E * math.cos(M) + 0.00026 * math.cos(Mp)
             - 0.00002 * math.cos(Mp - M) + 0.00002 * math.cos(Mp + M)
             + 0.00002 * math.cos(2 * F))
        corr += w if frac == 0.25 else -w
    return jde + corr


PHASE_EVENTS = {0.0: ("🌑", "Новий місяць", "Новомісяччя"),
                0.25: ("🌓", "Перша чверть", "ПершаЧверть"),
                0.5: ("🌕", "Повня", "Повня"),
                0.75: ("🌗", "Остання чверть", "ОстанняЧверть")}


def moon_info(d: date) -> dict:
    noon = datetime(d.year, d.month, d.day, 12, tzinfo=TZ)
    jd = _dt_to_jd(noon)
    k0 = math.floor((jd - 2451550.09766) / SYNODIC)

    # 1) подія фази, що припадає на цю добу (за Києвом)
    event = None
    for k in range(k0 - 2, k0 + 3):
        for q in (0.0, 0.25, 0.5, 0.75):
            moment = _jd_to_dt(_phase_jde(k + q)).astimezone(TZ)
            if moment.date() == d:
                emoji, name, tag = PHASE_EVENTS[q]
                event = {"emoji": emoji, "name": name, "tag": tag, "time": moment.strftime("%H:%M")}

    # 2) частка циклу: від попереднього молодика до наступного
    prev_new = max(_phase_jde(k) for k in range(k0 - 2, k0 + 3) if _phase_jde(k) <= jd)
    next_new = min(_phase_jde(k) for k in range(k0 - 2, k0 + 3) if _phase_jde(k) > jd)
    frac = (jd - prev_new) / (next_new - prev_new)
    age = jd - prev_new
    illum = (1 - math.cos(2 * math.pi * frac)) / 2

    if event:
        emoji, name, tag = event["emoji"], event["name"], event["tag"]
    else:
        for limit, e, n, t in ((0.25, "🌒", "Зростаючий серп (молодий місяць)", "МолодийМісяць"),
                               (0.50, "🌔", "Зростаючий місяць", "ЗростаючийМісяць"),
                               (0.75, "🌖", "Спадаючий місяць", "СпадаючийМісяць"),
                               (1.01, "🌘", "Спадаючий серп (старий місяць)", "СтарийМісяць")):
            if frac < limit:
                emoji, name, tag = e, n, t
                break
    return {"emoji": emoji, "name": name, "tag": tag, "event": event,
            "frac": frac, "age": age, "illum": illum}


# ═════════════════════════════════════════════════════════════════════════════
#  СОНЦЕ (формули NOAA) для Києва
# ═════════════════════════════════════════════════════════════════════════════
def sun_info(d: date) -> dict:
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat = math.radians(CITY_LAT)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl))
              - math.tan(lat) * math.tan(decl))
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))
    rise_utc = 720 - 4 * (CITY_LON + ha) - eqt        # хвилини від 00:00 UTC
    set_utc = 720 - 4 * (CITY_LON - ha) - eqt

    midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

    def local(minutes: float) -> datetime:
        return (midnight + timedelta(minutes=minutes)).astimezone(TZ)

    rise, sset = local(rise_utc), local(set_utc)
    length = int(round(set_utc - rise_utc))
    return {"sunrise": rise.strftime("%H:%M"), "sunset": sset.strftime("%H:%M"),
            "day_len": f"{length // 60} год {length % 60:02d} хв"}


# ═════════════════════════════════════════════════════════════════════════════
#  ЗБИРАННЯ ДАНИХ ДНЯ
# ═════════════════════════════════════════════════════════════════════════════
def _camel(tag: str) -> str:
    """День_Києва -> ДеньКиєва (єдиний стиль хештегів каналу)."""
    return "".join(p[:1].upper() + p[1:] for p in tag.split("_"))


def _split(item: str) -> tuple[str, str | None]:
    text, _, tag = item.partition("|")
    tag = tag.strip()
    return text.strip(), (_camel(tag) if tag else None)


def build_day(d: date) -> dict:
    key = d.strftime("%m-%d")
    state_raw = list(D.STATE.get(key, [])) + list(D.KYIV.get(key, []))
    church_raw = list(D.CHURCH.get(key, []))
    m_state, m_church = moveable_events(d)
    state_raw = m_state + state_raw
    church_raw = m_church + church_raw

    state = [_split(x) for x in state_raw]
    church = [_split(x) for x in church_raw]

    # легенда: спочатку під дату, інакше — з загального пулу
    if key in D.LEGENDS:
        legend = D.LEGENDS[key]
    else:
        legend = D.GENERAL_LEGENDS[d.timetuple().tm_yday % len(D.GENERAL_LEGENDS)]
    prykmety = D.PRYKMETY[d.month]
    prykmeta = prykmety[d.day % len(prykmety)]

    moon = moon_info(d)
    sun = sun_info(d)

    tags = list(BASE_TAGS) + [MONTH_TAG[d.month - 1], moon["tag"]]
    if key in D.NAMES:
        tags.append("Іменини")
    for _, t in state + church:
        if t:
            tags.append(t)
    seen, uniq = set(), []
    for t in tags:                                   # без дублів, збереження порядку
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)

    return {"date": d, "key": key, "weekday": WEEKDAYS[d.weekday()],
            "month_gen": MONTHS_GEN[d.month - 1],
            "state": state, "church": church, "names": D.NAMES.get(key),
            "legend": legend, "prykmeta": prykmeta, "moon": moon, "sun": sun,
            "tags": uniq}


# ═════════════════════════════════════════════════════════════════════════════
#  ФОРМАТУВАННЯ ПОСТУ (HTML для Telegram)
# ═════════════════════════════════════════════════════════════════════════════
def _e(s: str) -> str:
    return html.escape(s, quote=False)


def format_post(info: dict) -> str:
    d = info["date"]
    moon, sun = info["moon"], info["sun"]
    L: list[str] = []
    L.append(f"📅 <b>{info['weekday']}, {d.day} {info['month_gen']} {d.year}</b>")
    L.append("")

    if info["state"]:
        L.append("🎉 <b>Свята та пам'ятні дні</b>")
        L += [f"• {_e(t)}" for t, _ in info["state"]]
        L.append("")
    if info["church"]:
        L.append("⛪️ <b>Церковний календар</b>")
        L += [f"• {_e(t)}" for t, _ in info["church"]]
        L.append("")
    if info["names"]:
        L.append("🎂 <b>Іменини святкують</b>")
        L.append(_e(info["names"]))
        L.append("")
    if not info["state"] and not info["church"]:
        L.append("🌿 <i>Сьогодні без великих свят — звичайний день для добрих справ.</i>")
        L.append("")

    ev = moon["event"]
    moon_line = f"{moon['emoji']} <b>Місяць:</b> {_e(moon['name'])}"
    if ev:
        moon_line += f" (о {ev['time']})"
    L.append(moon_line)
    L.append(f"Освітленість диска ≈ {round(moon['illum'] * 100)}% · вік ≈ {moon['age']:.0f}-й день")
    L.append(f"🌅 Схід {sun['sunrise']} · 🌇 Захід {sun['sunset']} · день {sun['day_len']}  <i>(Київ)</i>")
    L.append("")

    title, text = info["legend"]
    L.append(f"📜 <b>Легенда дня: {_e(title)}</b>")
    L.append(f"<i>{_e(text)}</i>")
    L.append("")
    L.append(f"🌦 <b>Народна прикмета:</b> {_e(info['prykmeta'])}")
    L.append("")
    L.append(" ".join("#" + t for t in info["tags"][:12]))
    return "\n".join(L)


def format_caption(info: dict) -> str:
    d = info["date"]
    return (f"📅 <b>Щоденний календар · {d.day} {info['month_gen']} {d.year}</b>\n"
            f"{info['weekday']} · {info['moon']['emoji']} {_e(info['moon']['name'])}")


# ═════════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ═════════════════════════════════════════════════════════════════════════════
def _api(method: str, token: str, **kw):
    import requests
    url = f"https://api.telegram.org/bot{token}/{method}"
    last = None
    for attempt in range(1, 4):
        try:
            r = requests.post(url, timeout=60, **kw)
            data = r.json()
            if data.get("ok"):
                return data
            last = data
            if r.status_code == 429:                       # flood control
                time.sleep(data.get("parameters", {}).get("retry_after", 5) + 1)
                continue
            break
        except Exception as exc:                           # мережа
            last = {"error": str(exc)}
            time.sleep(3 * attempt)
    raise RuntimeError(f"Telegram {method} не вдався: {last}")


def send_message(token: str, chat_id: str, text: str):
    return _api("sendMessage", token,
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": "true",
                      "disable_notification": "true" if SILENT else "false"})


def send_photo(token: str, chat_id: str, path: str, caption: str):
    with open(path, "rb") as fh:
        return _api("sendPhoto", token,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
                          "disable_notification": "true" if SILENT else "false"},
                    files={"photo": fh})


# ═════════════════════════════════════════════════════════════════════════════
# СТАН І ЧАС
# ═════════════════════════════════════════════════════════════════════════════
def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mark_done(day: date) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_date": day.isoformat()}, f, ensure_ascii=False, indent=1)


def target_of(now: datetime) -> datetime:
    hh, mm = map(int, POST_AT.split(":"))
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def plain_len(html_text: str) -> int:
    """Довжина тексту без HTML-тегів — саме її рахує Telegram для ліміту підпису (1024)."""
    return len(re.sub(r"<[^>]+>", "", html_text))


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="Щоденний календар для Telegram-каналу «Київський не гідрометцентр»")
    ap.add_argument("--date", help="РРРР-ММ-ДД (за замовчуванням — сьогодні за Києвом)")
    ap.add_argument("--dry-run", action="store_true", help="не публікувати, лише показати")
    ap.add_argument("--force", action="store_true", help="публікувати негайно, ігноруючи вікно часу й відмітку «вже опубліковано»")
    ap.add_argument("--no-card", action="store_true", help="не створювати картку")
    ap.add_argument("--card-out", default="output/shchodennyy_kalendar_kyiv.png", help="куди зберегти картку")
    args = ap.parse_args()

    now = datetime.now(TZ)
    scheduled = os.getenv("GITHUB_EVENT_NAME") == "schedule" and not args.force and not args.dry_run

    # Планові запуски: перевіряємо «вже опубліковано» та вікно часу. Ручні запуски й --force — без перевірок.
    if scheduled:
        if load_state().get("last_date") == now.date().isoformat():
            print(f"Календар за {now.date()} уже опубліковано — вихід.")
            return 0
        target = target_of(now)
        if not target - timedelta(minutes=EARLY_MIN) <= now <= target + timedelta(minutes=LATE_MIN):
            print(f"Зараз {now:%H:%M} за Києвом — поза вікном публікації (ціль {POST_AT}). Пропускаю цей запуск.")
            return 0

    try:
        d = date.fromisoformat(args.date) if args.date else now.date()
    except ValueError:
        ap.error("Неправильна дата. Використовуйте формат РРРР-ММ-ДД.")
    info = build_day(d)
    text = format_post(info)

    card_path = None
    if not args.no_card:
        try:
            from shchodennyy_kalendar_card import generate_card
            os.makedirs(os.path.dirname(args.card_out) or ".", exist_ok=True)
            card_path = generate_card(info, args.card_out)
        except Exception as exc:  # картка — не критична
            print(f"⚠️ Картку не створено ({exc}). Публікую лише текст.", file=sys.stderr)

    if args.dry_run:
        print(text)
        print(f"\n— довжина тексту: {plain_len(text)} символів (ліміт підпису 1024)")
        if card_path:
            print("— картка збережена:", card_path)
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("❌ Не задано секрети TELEGRAM_BOT_TOKEN і CHAT_ID.", file=sys.stderr)
        return 1

    if scheduled:  # усе готово — чекаємо точної хвилини
        wait = (target_of(datetime.now(TZ)) - datetime.now(TZ)).total_seconds()
        if 0 < wait <= EARLY_MIN * 60:
            print(f"Усе готово. Чекаємо {int(wait // 60)} хв {int(wait % 60)} с до {POST_AT} за Києвом…")
            time.sleep(wait)

    posted = False
    if card_path:
        # Одне повідомлення: фото + повний текст у підписі. Якщо текст не влазить у 1024 —
        # фото з коротким підписом, а повний текст окремим повідомленням (нічого не обрізаємо).
        try:
            if plain_len(text) <= 1024:
                send_photo(token, chat_id, card_path, text)
            else:
                send_photo(token, chat_id, card_path, format_caption(info))
                mark_done_if_today(d, now)
                send_message(token, chat_id, text)
            posted = True
        except Exception as exc:
            print(f"⚠️ Не вдалося надіслати фото ({exc}). Пробую текстом.", file=sys.stderr)
    if not posted:
        send_message(token, chat_id, text)
    mark_done_if_today(d, now)
    print(f"✅ Опубліковано календар на {d.isoformat()} у каналі {CHANNEL_NAME}")
    return 0


def mark_done_if_today(d: date, now: datetime) -> None:
    if d == now.date():
        mark_done(d)


if __name__ == "__main__":
    sys.exit(main())
