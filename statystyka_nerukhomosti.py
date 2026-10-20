#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«Київська нерухомість: ціна квадратного метра» — щомісячний пост для «Київського не гідрометцентру».
https://t.me/kyyivskyy_ne_hidromettsentr

Джерело: статистика цін АН «Благовіст» — https://blagovist.ua/uk/realtystat/РРРР-ММ
  (за умовами сайту посилання на АН «Благовіст» обов'язкове, у пості воно є активним гіперпосиланням).

Що робить скрипт:
  • бере ПОВНИЙ попередній місяць (на 1-му числі поточного даних ще немає), порівнює з місяцем раніше й роком раніше;
  • показує ціну за м² по 10 районах (колонка «всі 1 м2» — єдина, що є справжнім агрегатом по району,
    див. нижче), загальні цифри по Києву та мікрорайони-рекордсмени;
  • нічого не вигадує: якщо джерело змінилося або даних не вистачає — публікації НЕ буде, а запуск стане червоним.

ВАЖЛИВО про джерело. У таблиці Благовіста значення «мін/серед/макс» для районів за кількістю кімнат
повторюють значення окремих мікрорайонів (напр. Деснянський = Троєщина, а «макс» Голосіївського для 1-кімн.
нижчий за «макс» його ж мікрорайону), тому як районні цифри вони ненадійні й тут НЕ використовуються.
Для «Київ» (весь) такі значення коректні — їх показуємо як «типово / від / до».

Змінні середовища: TELEGRAM_BOT_TOKEN (або BOT_TOKEN), CHAT_ID. Необов'язково: FORCE_RUN=1.
Запуск без відправки:  python statystyka_nerukhomosti.py --dry-run [--period 2026-09]
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from statystyka_nerukhomosti_card import render_micro_card, render_price_card

TZ = ZoneInfo("Europe/Kyiv")
SOURCE_URL = "https://blagovist.ua/uk/realtystat/{period}"
SOURCE_HOME = "https://blagovist.ua"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "statystyka_nerukhomosti_state.json")
CARD1 = os.path.join(HERE, "statystyka_nerukhomosti_card.png")
CARD2 = os.path.join(HERE, "statystyka_nerukhomosti_card_2.png")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "uk,en;q=0.8",
}
HASHTAGS = "#Київ #НерухомістьКиєва #ЦіниНаЖитло #КиївськийНеГідрометцентр"
log = logging.getLogger("nerukhomist")

DISTRICTS = ["Голосіївський", "Дарницький", "Деснянський", "Дніпровський", "Оболонський",
             "Печерський", "Подільський", "Святошинський", "Солом'янський", "Шевченківський"]
MONTHS = ["січень", "лютий", "березень", "квітень", "травень", "червень",
          "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
MONTHS_INS = ["січнем", "лютим", "березнем", "квітнем", "травнем", "червнем",
              "липнем", "серпнем", "вереснем", "жовтнем", "листопадом", "груднем"]
SQM_MIN, SQM_MAX = 0.3, 10.0        # прийнятна ціна м² у тис. $ — поза діапазоном вважаємо помилкою парсингу


class SourceError(RuntimeError):
    """Джерело недоступне, змінило структуру або має замало даних."""


# ── Допоміжне ──────────────────────────────────────────────────────────────
def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("’", "'").replace("ʼ", "'")).strip()


def parse_num(text: str) -> Optional[float]:
    t = re.sub(r"[\s\u00a0\u202f]+", "", text or "").replace(",", ".")
    return float(t) if re.fullmatch(r"\d+(?:\.\d+)?", t) else None


def shift_period(period: str, months: int) -> str:
    y, m = map(int, period.split("-"))
    idx = y * 12 + (m - 1) + months
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def period_label(period: str) -> str:
    y, m = period.split("-")
    return f"{MONTHS[int(m) - 1].capitalize()} {y}"


def default_period(today: date) -> str:
    """Останній ПОВНИЙ місяць: на 1-му числі поточний ще порожній."""
    return shift_period(f"{today.year}-{today.month:02d}", -1)


def money(v_thousand: float) -> str:
    """2.28 → '2 280' (тис. $ → $)."""
    return f"{round(v_thousand * 1000):,}".replace(",", "\u00a0")


def fnum(v: float) -> str:
    """1223.6 → '1\u00a0223,6'; 36.0 → '36'."""
    t = f"{v:,.1f}".replace(",", "\u00a0").replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def pct(new: float, old: float) -> Optional[float]:
    return (new / old - 1) * 100 if old else None


def fmt_pct(v: Optional[float], plus: bool = True) -> str:
    if v is None:
        return "—"
    sign = ("+" if v > 0 else "−" if v < 0 else "") if plus else ""
    return f"{sign}{abs(v):.1f}".replace(".", ",") + "%"


# ── Завантаження й розбір ──────────────────────────────────────────────────
def get_html(url: str, tries: int = 3) -> Optional[str]:
    last: Exception | None = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            last = e
            log.warning("GET %s не вдалося (спроба %d/%d): %s", url, i + 1, tries, e)
            time.sleep(3 * (i + 1))
    raise SourceError(f"Не вдалося завантажити {url}: {last}")


def parse_table(page: str) -> dict:
    """Повертає {'city': row, 'districts': {назва: row}, 'micro': [row…]}.
    Таблиця: Район | 1к(мін,серед,макс,1м²) | 2к(…) | 3к(…) | всі 1м² — разом 14 клітинок (суми в тис. $)."""
    soup = BeautifulSoup(page, "html.parser")
    city, districts, micro, parent, seen14 = None, {}, [], None, False
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 14:
            continue
        seen14 = True
        name = norm_name(cells[0])
        nums = [parse_num(x) for x in cells[1:14]]
        if not name or name.lower() == "район" or nums[12] is None:
            continue
        row = {"name": name, "sqm": nums[12], "rooms": {
            k: {"min": nums[i], "avg": nums[i + 1], "max": nums[i + 2], "sqm": nums[i + 3]}
            for k, i in ((1, 0), (2, 4), (3, 8))}}
        base = re.sub(r"\s+район$", "", name, flags=re.IGNORECASE)
        if name == "Київ":
            city = row
        elif name.lower().endswith(" район") and base in DISTRICTS:
            row["name"], parent = base, base
            districts[base] = row
        else:
            row["parent"] = parent
            row["n_rooms"] = sum(1 for r in row["rooms"].values() if r["avg"] is not None)
            micro.append(row)
    if not seen14:
        raise SourceError("У таблиці немає рядків із 14 колонками — структура сторінки змінилась.")
    return {"city": city, "districts": districts, "micro": micro}


def validate(data: dict, period: str) -> None:
    miss = [d for d in DISTRICTS if d not in data["districts"]]
    if data["city"] is None or miss:
        raise SourceError(f"{period}: бракує даних (рядок «Київ»: {data['city'] is not None}, немає районів: {miss}).")
    bad = [(n, r["sqm"]) for n, r in data["districts"].items() if not SQM_MIN <= r["sqm"] <= SQM_MAX]
    if bad or not SQM_MIN <= data["city"]["sqm"] <= SQM_MAX:
        raise SourceError(f"{period}: підозрілі значення ціни за м²: {bad or data['city']['sqm']}")


def load_period(period: str, required: bool) -> Optional[dict]:
    page = get_html(SOURCE_URL.format(period=period))
    if page is None:
        if required:
            raise SourceError(f"Сторінка за {period} не знайдена.")
        return None
    try:
        data = parse_table(page)
        validate(data, period)
        return data
    except SourceError:
        if required:
            raise
        log.warning("Порівняльний місяць %s пропущено (немає повних даних).", period)
        return None


# ── Збірка аналітики ───────────────────────────────────────────────────────
def analyze(cur: dict, prev: Optional[dict], yoy: Optional[dict]) -> dict:
    def delta(name: Optional[str], base: Optional[dict]) -> Optional[float]:
        if not base:
            return None
        a = cur["city"]["sqm"] if name is None else cur["districts"][name]["sqm"]
        b = base["city"]["sqm"] if name is None else base["districts"].get(name, {}).get("sqm")
        return pct(a, b) if b else None

    ds = sorted(({"name": n, "sqm": r["sqm"] * 1000, "mom": delta(n, prev), "yoy": delta(n, yoy)}
                 for n, r in cur["districts"].items()), key=lambda x: -x["sqm"])
    rooms = {k: v for k, v in cur["city"]["rooms"].items() if v["avg"] is not None}
    # мікрорайони: беремо лише ті, де є дані щонайменше за двома типами квартир (проти «тонких» вибірок)
    micro = [m for m in cur["micro"] if m.get("n_rooms", 0) >= 2]
    micro.sort(key=lambda m: -m["sqm"])
    return {"districts": ds,
            "city": {"sqm": cur["city"]["sqm"] * 1000, "mom": delta(None, prev), "yoy": delta(None, yoy), "rooms": rooms},
            "top": micro[:6], "bottom": micro[::-1][:6]}


# ── Текст ──────────────────────────────────────────────────────────────────
def build_text(a: dict, period: str) -> str:
    e = lambda t: html.escape(t, quote=False)
    y, mo = period.split("-")
    prev_ins = MONTHS_INS[(int(mo) - 2) % 12]
    c, ds = a["city"], a["districts"]
    url = SOURCE_URL.format(period=period)
    L = [f"🏙️ <b>Київська нерухомість: ціна квадратного метра</b>",
         f"📅 {period_label(period)} · дані <a href=\"{url}\">АН «Благовіст»</a>", ""]

    head = f"У середньому по Києву — <b>${money(c['sqm'] / 1000)} за м²</b>"
    bits = []
    if c["mom"] is not None:
        bits.append(f"{fmt_pct(c['mom'])} порівняно з {prev_ins}")
    if c["yoy"] is not None:
        bits.append(f"{fmt_pct(c['yoy'])} за рік")
    L.append(head + (f" ({', '.join(bits)})." if bits else "."))
    ratio = ds[0]["sqm"] / ds[-1]["sqm"]
    L.append(f"Між найдорожчим ({e(ds[0]['name'])}) і найдешевшим ({e(ds[-1]['name'])}) районом — "
             f"різниця у {str(round(ratio, 1)).replace('.', ',')} раза.")
    L += ["", "📊 <b>Райони за ціною м²</b> <i>(зміна: до попереднього місяця · за рік)</i>"]
    rows = []
    for d in ds:
        rows.append(f"{d['name']:<14} {'$' + money(d['sqm'] / 1000):>7}  {fmt_pct(d['mom']):>6} {fmt_pct(d['yoy']):>7}")
    L.append("<pre>" + e("\n".join(rows)) + "</pre>")

    if c["rooms"]:
        L += ["", "🏠 <b>Квартири по Києву</b> <i>(тис. $: типово · від · до)</i>"]
        for k, r in sorted(c["rooms"].items()):
            L.append(f"▪️ {k}-кімн.: <b>{fnum(r['avg'])}</b> · від {fnum(r['min'])} до {fnum(r['max'])}")
        L.append("<i>«Від» і «до» — крайні значення, часто поодинокі об'єкти; орієнтуватися варто на «типово».</i>")

    if a["top"] and a["bottom"]:
        top = ", ".join(f"{e(m['name'])} ${money(m['sqm'])}" for m in a["top"][:3])
        low = ", ".join(f"{e(m['name'])} ${money(m['sqm'])}" for m in a["bottom"][:3])
        L += ["", f"🔺 <b>Найдорожчі мікрорайони:</b> {top}", f"🔻 <b>Найдешевші:</b> {low}"]

    L += ["",
          "💡 <b>Як читати ці цифри?</b>",
          "Це статистика з бази однієї агенції, а не офіційні дані про угоди й не весь ринок. "
          "Ціна м² — орієнтир для порівняння районів; реальна вартість залежить від будинку, стану, поверху й торгу. "
          "Зміни за місяць у такій вибірці можуть бути «шумом».",
          "", f"📌 Джерело: <a href=\"{SOURCE_HOME}\">АН «Благовіст»</a> ({SOURCE_HOME.split('//')[1]}).",
          "", HASHTAGS]
    return "\n".join(L)


# ── Telegram ───────────────────────────────────────────────────────────────
def tg(method: str, token: str, **kw) -> dict:
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=90, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def publish(token: str, chat_id: str, cards: list[str], text: str) -> None:
    files = {f"p{i}": open(p, "rb") for i, p in enumerate(cards)}
    try:
        media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(cards))]
        tg("sendMediaGroup", token, data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)
    finally:
        for f in files.values():
            f.close()
    tg("sendMessage", token, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"})


# ── Стан ───────────────────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати й не зберігати стан")
    ap.add_argument("--period", help="РРРР-ММ (за замовчуванням — останній повний місяць)")
    ap.add_argument("--force", action="store_true", help="публікувати, навіть якщо цей місяць уже опубліковано")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    period = args.period or os.getenv("PERIOD") or default_period(date.today())
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        log.error("Некоректний період «%s», потрібен формат РРРР-ММ.", period)
        return 1
    force = args.force or os.getenv("FORCE_RUN") == "1"
    state = load_state()
    if not args.dry_run and not force and state.get("last_period") == period:
        log.info("За %s уже опубліковано — вихід.", period)
        return 0

    try:
        cur = load_period(period, required=True)
        time.sleep(1)
        prev = load_period(shift_period(period, -1), required=False)
        time.sleep(1)
        yoy = load_period(shift_period(period, -12), required=False)
    except SourceError as e:
        log.error("Публікації не буде: %s", e)
        return 1

    a = analyze(cur, prev, yoy)
    label = period_label(period)
    render_price_card(a, label, CARD1)
    render_micro_card(a, label, CARD2)
    text = build_text(a, period)
    if len(text) > 4096:
        log.error("Текст задовгий (%d символів).", len(text))
        return 1

    if args.dry_run:
        print(re.sub(r"</?(b|i|pre)>|<a href=\"[^\"]*\">|</a>", "", text))
        log.info("Dry-run: картки збережено (%s, %s), текст %d символів.", CARD1, CARD2, len(text))
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id:
        log.error("Не задано TELEGRAM_BOT_TOKEN / CHAT_ID")
        return 1
    publish(token, chat_id, [CARD1, CARD2], text)
    save_state({"last_period": period})
    log.info("Опубліковано за %s.", period)
    return 0


if __name__ == "__main__":
    sys.exit(main())
