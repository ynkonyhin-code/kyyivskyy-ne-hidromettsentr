# -*- coding: utf-8 -*-
"""Щоденний календар для Telegram-каналу «Київський не гідрометцентр».

Готує календарний допис українською, обчислює фази Місяця та схід/захід Сонця
для Києва, малює PNG-картку та надсилає картку й текст у Telegram.

Локальний тест без публікації:
    python shchodennyy_kalendar.py --dry-run
    python shchodennyy_kalendar.py --date 2026-12-25 --dry-run
    python shchodennyy_kalendar.py --force

GitHub Secrets: TELEGRAM_BOT_TOKEN, CHAT_ID.
Для сумісності підтримуються також BOT_TOKEN і старе ім'я SUMY_BOT_TOKEN.
"""
from __future__ import annotations

import argparse
import html
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import shchodennyy_kalendar_data as D

TZ = ZoneInfo("Europe/Kyiv")
POST_HOUR = 10
CITY_LAT, CITY_LON = 50.4501, 30.5234
CHANNEL_NAME = "Київський не гідрометцентр"
CHANNEL_URL = "https://t.me/kyyivskyy_ne_hidromettsentr"
BASE_TAGS = ["Календар", "ЩоденнийКалендар", "КиївськийНеГідрометцентр", "Київ", "Київщина"]
MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
MONTH_TAG = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
WEEKDAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]


def orthodox_easter(year: int) -> date:
    """Православний Великдень за юліанською пасхалією (1900–2099)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return date(year, month, day) + timedelta(days=13)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-й день тижня місяця; weekday: 0=понеділок, -1 у n означає останній."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def moveable_events(d: date) -> tuple[list[str], list[str]]:
    state: list[str] = []
    church: list[str] = []
    easter = orthodox_easter(d.year)
    offset = (d - easter).days
    church_offsets = {
        -49: "Прощена неділя — завершення Масниці|Масниця",
        -48: "Початок Великого посту|ВеликийПіст",
        -7: "Вербна неділя|ВербнаНеділя",
        -3: "Великий четвер|ВеликийТиждень",
        -2: "Страсна п'ятниця|ВеликийТиждень",
        -1: "Страсна субота|ВеликийТиждень",
        0: "Великдень — Воскресіння Христове ✝️|Великдень",
        1: "Світлий понеділок|Великдень",
        7: "Томина неділя|ТоминаНеділя",
        39: "Вознесіння Господнє|Вознесіння",
        49: "Трійця — Зелені свята 🌿|Трійця",
        50: "День Святого Духа|ДеньСвятогоДуха",
    }
    if offset in church_offsets:
        church.append(church_offsets[offset])
    elif -55 <= offset <= -50:
        church.append("Масниця — сирний тиждень|Масниця")
    elif -47 <= offset <= -8:
        church.append("Триває Великий піст|ВеликийПіст")

    # Рухомі державні й тематичні дні.
    movable_state = {
        nth_weekday(d.year, 5, 6, 2): "День матері в Україні|ДеньМатері",
        nth_weekday(d.year, 5, 3, 3): "День вишиванки 🇺🇦|ДеньВишиванки",
        nth_weekday(d.year, 5, 6, -1): "День Києва 🏙|ДеньКиєва",
        nth_weekday(d.year, 6, 6, 3): "День батька|ДеньБатька",
        nth_weekday(d.year, 10, 6, 1): "День працівників освіти України|ДеньОсвіти",
        nth_weekday(d.year, 11, 5, 4): "День пам'яті жертв Голодомору 🕯|Голодомор",
    }
    if d in movable_state:
        state.append(movable_state[d])
    return state, church


# Модель фаз Місяця: опорний молодик 2000-01-06 18:14 UTC та синодичний місяць.
NEW_MOON_EPOCH = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
SYNODIC_DAYS = 29.530588861
PHASE_NAMES = [
    (0.03, "🌑", "Новий Місяць", "НовийМісяць"),
    (0.22, "🌒", "Молодий Місяць зростає", "МолодийМісяць"),
    (0.28, "🌓", "Перша чверть", "ПершаЧверть"),
    (0.47, "🌔", "Місяць зростає", "ЗростаючийМісяць"),
    (0.53, "🌕", "Повня", "Повня"),
    (0.72, "🌖", "Місяць спадає", "СпадаючийМісяць"),
    (0.78, "🌗", "Остання чверть", "ОстанняЧверть"),
    (0.97, "🌘", "Старий Місяць", "СтарийМісяць"),
    (1.01, "🌘", "Старий Місяць", "СтарийМісяць"),
]
PHASE_EVENTS = [(0.0, "🌑", "Новий Місяць", "НовийМісяць"), (0.25, "🌓", "Перша чверть", "ПершаЧверть"), (0.5, "🌕", "Повня", "Повня"), (0.75, "🌗", "Остання чверть", "ОстанняЧверть")]


def moon_info(d: date) -> dict:
    local_noon = datetime(d.year, d.month, d.day, 12, tzinfo=TZ)
    cycle = ((local_noon.astimezone(timezone.utc) - NEW_MOON_EPOCH).total_seconds() / 86400) % SYNODIC_DAYS
    frac = cycle / SYNODIC_DAYS
    illumination = (1 - math.cos(2 * math.pi * frac)) / 2
    def phase_distance(target: float) -> float:
        raw = abs(frac - target)
        return min(raw, 1.0 - raw)
    nearest = min(PHASE_EVENTS, key=lambda p: phase_distance(p[0]))
    event = None
    # Час фази приблизний; показуємо його лише коли сама подія близько.
    distance = phase_distance(nearest[0])
    if distance < 0.018:
        phase_day = nearest[0] * SYNODIC_DAYS
        delta_days = phase_day - cycle
        if delta_days < -SYNODIC_DAYS / 2:
            delta_days += SYNODIC_DAYS
        elif delta_days > SYNODIC_DAYS / 2:
            delta_days -= SYNODIC_DAYS
        moment = local_noon + timedelta(days=delta_days)
        if moment.astimezone(TZ).date() == d:
            event = {"emoji": nearest[1], "name": nearest[2], "tag": nearest[3], "time": moment.strftime("%H:%M")}
    chosen = next((p for p in PHASE_NAMES if frac < p[0]), PHASE_NAMES[-1])
    if event:
        emoji, name, tag = event["emoji"], event["name"], event["tag"]
    else:
        emoji, name, tag = chosen[1], chosen[2], chosen[3]
    return {"emoji": emoji, "name": name, "tag": tag, "event": event, "frac": frac,
            "age": cycle, "illum": illumination}


def sun_info(d: date) -> dict:
    """Оцінка сходу/заходу Сонця за наближеними формулами NOAA для Києва."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat = math.radians(CITY_LAT)
    cos_ha = math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl)) - math.tan(lat) * math.tan(decl)
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))
    rise_utc = 720 - 4 * (CITY_LON + ha) - eqt
    set_utc = 720 - 4 * (CITY_LON - ha) - eqt
    midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    rise = (midnight + timedelta(minutes=rise_utc)).astimezone(TZ)
    sunset = (midnight + timedelta(minutes=set_utc)).astimezone(TZ)
    length = int(round(set_utc - rise_utc))
    return {"sunrise": rise.strftime("%H:%M"), "sunset": sunset.strftime("%H:%M"),
            "day_len": f"{length // 60} год {length % 60:02d} хв"}


def split_item(item: str) -> tuple[str, str | None]:
    text, _, tag = item.partition("|")
    return text.strip(), tag.strip() or None


def build_day(d: date) -> dict:
    key = d.strftime("%m-%d")
    state_raw = list(D.STATE.get(key, [])) + list(D.KYIV.get(key, []))
    church_raw = list(D.CHURCH.get(key, []))
    movable_state, movable_church = moveable_events(d)
    state_raw = movable_state + state_raw
    church_raw = movable_church + church_raw
    state = [split_item(x) for x in state_raw]
    church = [split_item(x) for x in church_raw]
    legend = D.LEGENDS.get(key) or D.GENERAL_LEGENDS[d.timetuple().tm_yday % len(D.GENERAL_LEGENDS)]
    monthly_signs = D.PRYKMETY[d.month]
    sign = monthly_signs[(d.day - 1) % len(monthly_signs)]
    moon = moon_info(d)
    sun = sun_info(d)
    tags = BASE_TAGS + [MONTH_TAG[d.month - 1], moon["tag"]]
    if key in D.NAMES:
        tags.append("Іменини")
    for _, tag in state + church:
        if tag:
            tags.append(tag)
    unique_tags, seen = [], set()
    for tag in tags:
        if tag.lower() not in seen:
            unique_tags.append(tag)
            seen.add(tag.lower())
    return {"date": d, "key": key, "weekday": WEEKDAYS[d.weekday()], "month_gen": MONTHS_GEN[d.month - 1],
            "state": state, "church": church, "names": D.NAMES.get(key), "legend": legend,
            "prykmeta": sign, "moon": moon, "sun": sun, "tags": unique_tags}


def esc(value: str) -> str:
    return html.escape(str(value), quote=False)


def format_post(info: dict) -> str:
    d, moon, sun = info["date"], info["moon"], info["sun"]
    lines = [f"📅 {info['weekday']}, {d.day} {info['month_gen']} {d.year}", ""]
    if info["state"]:
        lines += ["🎉 Свята та пам'ятні дні"] + [f"• {esc(t)}" for t, _ in info["state"]] + [""]
    if info["church"]:
        lines += ["⛪️ Церковний календар"] + [f"• {esc(t)}" for t, _ in info["church"]] + [""]
    if info["names"]:
        lines += ["🎂 Іменини святкують", esc(info["names"]), ""]
    if not info["state"] and not info["church"]:
        lines += ["🌿 Сьогодні без великих свят — день для добрих справ.", ""]
    moon_line = f"{moon['emoji']} Місяць: {esc(moon['name'])}"
    if moon["event"]:
        moon_line += f" (орієнтовно о {moon['event']['time']})"
    lines += [moon_line,
              f"Освітленість диска ≈ {round(moon['illum'] * 100)}% · вік ≈ {moon['age']:.1f} доби",
              f"🌅 Схід {sun['sunrise']} · 🌇 Захід {sun['sunset']} · тривалість дня {sun['day_len']} (Київ)", ""]
    title, story = info["legend"]
    lines += [f"📜 Легенда дня: {esc(title)}", esc(story), "", f"🌦 Народна прикмета: {esc(info['prykmeta'])}", "",
              " ".join("#" + t for t in info["tags"][:12])]
    return "\n".join(lines)


def format_caption(info: dict) -> str:
    d = info["date"]
    return f"📅 Щоденний календар · {d.day} {info['month_gen']} {d.year}\n{info['weekday']} · {info['moon']['emoji']} {esc(info['moon']['name'])}"


def telegram_api(method: str, token: str, **kwargs):
    import requests
    url = f"https://api.telegram.org/bot{token}/{method}"
    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.post(url, timeout=60, **kwargs)
            try:
                payload = response.json()
            except ValueError:
                payload = {"error": f"HTTP {response.status_code}: {response.text[:300]}"}
            if response.ok and payload.get("ok"):
                return payload
            last_error = payload
            if response.status_code == 429:
                time.sleep(payload.get("parameters", {}).get("retry_after", 5) + 1)
                continue
            break
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2 * attempt)
    raise RuntimeError(f"Telegram {method} не вдався: {last_error}")


def send_message(token: str, chat_id: str, message: str):
    return telegram_api("sendMessage", token, data={"chat_id": chat_id, "text": message,
                          "parse_mode": "HTML", "disable_web_page_preview": "true"})


def send_photo(token: str, chat_id: str, path: str, caption: str):
    with open(path, "rb") as photo:
        return telegram_api("sendPhoto", token, data={"chat_id": chat_id, "caption": caption,
                              "parse_mode": "HTML"}, files={"photo": photo})


def main() -> int:
    parser = argparse.ArgumentParser(description="Щоденний календар для Київського не гідрометцентру")
    parser.add_argument("--date", help="Дата РРРР-ММ-ДД; за замовчуванням — сьогодні за Києвом")
    parser.add_argument("--dry-run", action="store_true", help="Не публікувати, лише сформувати й показати допис")
    parser.add_argument("--force", action="store_true", help="Ігнорувати перевірку години 10:00")
    parser.add_argument("--no-card", action="store_true", help="Не створювати PNG-картку")
    parser.add_argument("--card-out", default="output/shchodennyy_kalendar_kyiv.png", help="Шлях до PNG-картки")
    args = parser.parse_args()
    now = datetime.now(TZ)
    if os.getenv("GITHUB_EVENT_NAME") == "schedule" and not args.force and now.hour != POST_HOUR:
        print(f"Зараз {now:%H:%M} за Києвом — публікація запланована на {POST_HOUR}:00. Пропускаю цей запуск.")
        return 0
    try:
        day = date.fromisoformat(args.date) if args.date else now.date()
    except ValueError:
        parser.error("Неправильна дата. Використовуйте формат РРРР-ММ-ДД.")
    info = build_day(day)
    post = format_post(info)
    card_path = None
    if not args.no_card:
        try:
            from shchodennyy_kalendar_card import generate_card
            os.makedirs(os.path.dirname(args.card_out) or ".", exist_ok=True)
            card_path = generate_card(info, args.card_out)
        except Exception as exc:
            print(f"⚠️ Не вдалося створити картку ({exc}); продовжую з текстовим дописом.", file=sys.stderr)
    if args.dry_run:
        print(post)
        print(f"\n— довжина тексту: {len(post)} символів")
        if card_path:
            print(f"— картку збережено: {card_path}")
        return 0
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("SUMY_BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("❌ Не задано секрети TELEGRAM_BOT_TOKEN і CHAT_ID (або сумісні альтернативні назви).", file=sys.stderr)
        return 1
    if card_path:
        send_photo(token, chat_id, card_path, format_caption(info))
    send_message(token, chat_id, post)
    print(f"✅ Опубліковано календар для Києва на {day.isoformat()} у каналі {CHANNEL_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
