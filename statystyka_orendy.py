#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«Оренда квартир у Києві» — щомісячний пост для «Київського не гідрометцентру».
https://t.me/kyyivskyy_ne_hidromettsentr

Джерело: статистика цін на оренду DIM.RIA — https://dom.ria.com/uk/arenda-kvartir/kiev/ceny/
(ціни з активних оголошень, оновлюється щодня; у пості — активне посилання на джерело).

Сторінка DIM.RIA — Vue-застосунок: у «сирому» HTML є лише перший район, решта підвантажується кліком.
Тому дані збирає headless-браузер (Playwright): вмикає «грн», відкриває «Всі райони», потім по черзі кожен
із 10 районів і ЧЕКАЄ, доки обидві таблиці (середня ціна й ціни за кімнатністю) стануть узгодженими —
інакше можна прочитати «половину старого стану» (так буває: таблиця району вже оновилась, а таблиця
кімнатності — ще ні). Якщо щось не сходиться, публікації НЕ буде, а запуск стане червоним.

Динаміка: DIM.RIA для кожного району дає напрям за місяць (дорожчає / дешевшає / без змін) — беремо його одразу;
свої відсотки рахуємо порівнянням із попереднім місячним знімком (statystyka_orendy_state.json).

Змінні середовища: TELEGRAM_BOT_TOKEN (або BOT_TOKEN), CHAT_ID. Необов'язково: FORCE_RUN=1.
Запуск без відправки:  python statystyka_orendy.py --dry-run [--debug]
Тест без браузера:     python statystyka_orendy.py --dry-run --from-dir ДИРЕКТОРІЯ_ЗІ_ЗБЕРЕЖЕНИМИ_HTML
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
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from statystyka_orendy_card import render_heat_card, render_main_card

TZ = ZoneInfo("Europe/Kyiv")
URL = "https://dom.ria.com/uk/arenda-kvartir/kiev/ceny/"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "statystyka_orendy_state.json")
CARD1 = os.path.join(HERE, "statystyka_orendy_card.png")
CARD2 = os.path.join(HERE, "statystyka_orendy_card_2.png")
DEBUG_DIR = os.path.join(HERE, "orenda_debug")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
HASHTAGS = "#Київ #ОрендаКвартир #ОрендаКиїв #ЦіниНаЖитло #КиївськийНеГідрометцентр"
log = logging.getLogger("orenda")

DISTRICTS = ["Голосіївський", "Дарницький", "Деснянський", "Дніпровський", "Оболонський",
             "Печерський", "Подільський", "Святошинський", "Солом'янський", "Шевченківський"]
MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня",
              "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
AVG_RANGE = (3_000, 250_000)       # прийнятна середня оренда за квартиру, грн/міс
ROOM_RANGE = (2_000, 600_000)      # прийнятна оренда окремої кімнатності, грн/міс
CHANGE_TITLES = {"Зменшення середньої ціни": "down", "Середня ціна без змін": "same",
                 "Збільшення середньої ціни": "up"}


class ScrapeError(RuntimeError):
    """Не вдалося отримати узгоджені дані з джерела."""


# ── Розбір HTML (чисті функції — перевіряються на збережених сторінках) ─────────
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ").replace("’", "'").replace("ʼ", "'")).strip()


def parse_uah(text: str) -> Optional[int]:
    t = norm(text)
    if t in ("", "-", "—", "–"):
        return None
    if "грн" not in t:
        raise ScrapeError(f"Очікувалися гривні, а отримано «{t}» — не спрацював перемикач валюти.")
    digits = re.sub(r"\D", "", t.replace("грн", ""))
    return int(digits) if digits else None


def _tables(page: str) -> list:
    return BeautifulSoup(page, "html.parser").find_all("table")


def parse_all(page: str) -> dict[str, int]:
    """Вкладка «Всі райони»: {район: середня оренда за квартиру, грн/міс}."""
    ts = _tables(page)
    if not ts:
        raise ScrapeError("На сторінці немає таблиць.")
    out = {}
    for tr in ts[0].find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) == 2:
            out[norm(cells[0].get_text(" ", strip=True))] = parse_uah(cells[1].get_text(" ", strip=True))
    missing = [d for d in DISTRICTS if out.get(d) is None]
    if missing:
        raise ScrapeError(f"У вкладці «Всі райони» бракує районів: {missing}")
    return {d: out[d] for d in DISTRICTS}


def parse_district(page: str, district: str) -> dict[int, Optional[int]]:
    """Таблиця «за кімнатністю»: перший рядок даних — сам район. Повертає {1: грн, 2: …, 3: …, 4: …}.
    Падає, якщо рядок належить іншому району (стара/неузгоджена таблиця)."""
    ts = _tables(page)
    if len(ts) < 2:
        raise ScrapeError("Немає таблиці цін за кімнатністю.")
    rows = ts[1].find_all("tr")
    if len(rows) < 2:
        raise ScrapeError("Таблиця кімнатності порожня.")
    cells = rows[1].find_all(["td", "th"])
    if len(cells) < 5:
        raise ScrapeError("Незвична кількість колонок у таблиці кімнатності.")
    if not norm(cells[0].get_text(" ", strip=True)).startswith(district):
        raise ScrapeError(f"Таблиця кімнатності належить іншому району (очікували «{district}», "
                          f"є «{norm(cells[0].get_text(' ', strip=True))[:30]}…»).")
    return {k: parse_uah(cells[k].get_text(" ", strip=True)) for k in (1, 2, 3, 4)}


def parse_changes(page: str) -> dict[str, str]:
    """{район: 'up' | 'down' | 'same'} зі списків «зміна за останній місяць». Немає в списках → пропуск."""
    soup = BeautifulSoup(page, "html.parser")
    out: dict[str, str] = {}
    for title, key in CHANGE_TITLES.items():
        node = soup.find(string=re.compile(re.escape(title)))
        ul = node.find_parent().find_next("ul") if node else None
        for li in (ul.find_all("li") if ul else []):
            name = norm(li.get_text(" ", strip=True))
            if name in DISTRICTS:
                out[name] = key
    return out


def parse_meta(page: str) -> dict:
    text = norm(BeautifulSoup(page, "html.parser").get_text(" "))
    rate = re.search(r"Купівля\s*([\d.,]+)\s*Продаж\s*([\d.,]+)", text)
    cnt = re.search(r"на підставі\s+([\d\s]+?)\s+активних оголошень", text)
    return {"rate": float(rate.group(2).replace(",", ".")) if rate else None,
            "listings": int(re.sub(r"\D", "", cnt.group(1))) if cnt else None}


def validate(data: dict) -> None:
    for d in DISTRICTS:
        a = data["avg"][d]
        if not AVG_RANGE[0] <= a <= AVG_RANGE[1]:
            raise ScrapeError(f"{d}: підозріла середня оренда {a} грн.")
        rooms = data["rooms"][d]
        if all(v is None for v in rooms.values()):
            raise ScrapeError(f"{d}: немає жодної ціни за кімнатністю.")
        for k, v in rooms.items():
            if v is not None and not ROOM_RANGE[0] <= v <= ROOM_RANGE[1]:
                raise ScrapeError(f"{d}, {k}-кімн.: підозріла ціна {v} грн.")
        if rooms[1] is None:
            raise ScrapeError(f"{d}: немає ціни однокімнатної — порівняння районів некоректне.")


# ── Збір даних браузером ───────────────────────────────────────────────────────
JS_ALL = """(names) => { const t = document.querySelector('table'); if (!t) return false;
  const rows = [...t.rows].filter(r => r.cells.length === 2);
  const got = rows.map(r => r.cells[0].innerText.replace(/[’ʼ]/g, "'").trim());
  return rows.length === names.length && names.every(n => got.includes(n)) && rows[0].innerText.includes('грн'); }"""
_FIX = "const fix = s => s.replace(/[’ʼ]/g, \"'\").replace(/\\s+/g, ' ').trim();"
JS_T0 = "(d) => {" + _FIX + """ const t = document.querySelector('table');
  return !!t && !!t.rows[0] && fix(t.rows[0].cells[0].innerText) === d; }"""
JS_T1 = "(d) => {" + _FIX + """ const ts = document.querySelectorAll('table'); if (ts.length < 2) return false;
  const r = ts[1].rows[1]; return !!r && r.cells.length >= 5 && fix(r.cells[0].innerText).startsWith(d); }"""
JS_DIAG = "() => {" + _FIX + """ const ts = document.querySelectorAll('table');
  return {tables: ts.length,
    t0_first: ts[0] && ts[0].rows[0] ? fix(ts[0].rows[0].innerText).slice(0, 60) : null,
    t1_first: ts[1] && ts[1].rows[1] ? fix(ts[1].rows[1].innerText).slice(0, 80) : null,
    active: [...document.querySelectorAll('button.link-element.active')].map(b => fix(b.innerText))}; }"""


def _button(page, name: str):
    pattern = re.compile(r"^\s*" + re.escape(name).replace("'", "['’ʼ]") + r"\s*$")
    return page.locator("button.link-element").filter(has_text=pattern).first


def _diag(page) -> str:
    try:
        return json.dumps(page.evaluate(JS_DIAG), ensure_ascii=False)
    except Exception as e:                       # діагностика не повинна ламати основну помилку
        return f"(діагностика недоступна: {e})"


def _open_district(page, d: str) -> str:
    """Клік по вкладці району → чекаємо спершу таблицю середніх цін, потім (прокрутивши сторінку до неї —
    таблиця кімнатності нижче першого екрана й може підвантажуватись лише тоді) таблицю кімнатності."""
    from playwright.sync_api import TimeoutError as PWTimeout
    last = ""
    for attempt in (1, 2):
        if attempt == 2:                          # «пінок»: інша вкладка й назад
            _button(page, "Всі райони").click()
            page.wait_for_function(JS_ALL, arg=DISTRICTS, timeout=15_000)
        _button(page, d).click()
        try:
            page.wait_for_function(JS_T0, arg=d, timeout=20_000)
            page.locator("table").nth(1).scroll_into_view_if_needed()
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except PWTimeout:
                pass
            page.wait_for_function(JS_T1, arg=d, timeout=25_000)
            page.wait_for_timeout(600)            # дати дозавантажитись останнім клітинкам
            return page.content()
        except PWTimeout:
            last = _diag(page)
            log.warning("Район «%s», спроба %d: таблиці не узгодились. Стан: %s", d, attempt, last)
    raise ScrapeError(f"таблиці району «{d}» не узгодились за 2 спроби; стан сторінки: {last}")


def scrape_live(debug: bool = False) -> dict[str, str]:
    """Повертає {'all': html, <район>: html, …} — знімки сторінки після кожного кліку."""
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    snaps: dict[str, str] = {}
    os.makedirs(DEBUG_DIR, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(locale="uk-UA", timezone_id="Europe/Kyiv", user_agent=UA,
                                  viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        step = "відкриття сторінки"
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector("table", timeout=45_000)
            try:                                    # банер cookie, якщо є
                page.get_by_role("button", name=re.compile("Дозволити всі")).first.click(timeout=4_000)
            except Exception:
                pass
            step = "перемикач «грн»"
            page.locator("label.tabs-item").filter(has_text=re.compile(r"^\s*грн\s*$")).first.click()
            page.wait_for_function("() => document.querySelector('table').innerText.includes('грн')")
            step = "вкладка «Всі райони»"
            _button(page, "Всі райони").click()
            page.wait_for_function(JS_ALL, arg=DISTRICTS)
            snaps["all"] = page.content()
            for d in DISTRICTS:
                step = f"район «{d}»"
                snaps[d] = _open_district(page, d)
                log.info("Зібрано: %s", d)
            if debug:
                for k, v in snaps.items():
                    with open(os.path.join(DEBUG_DIR, f"{k}.html"), "w", encoding="utf-8") as f:
                        f.write(v)
        except Exception as e:                       # діагностика для розбору «що змінилось на сайті»
            try:
                page.screenshot(path=os.path.join(DEBUG_DIR, "fail.png"), full_page=False)
                with open(os.path.join(DEBUG_DIR, "fail.html"), "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            kind = "тайм-аут" if isinstance(e, PWTimeout) else type(e).__name__
            raise ScrapeError(f"Збій на кроці «{step}» ({kind}): {str(e)[:600]}") from e
        finally:
            browser.close()
    return snaps


def load_from_dir(path: str) -> dict[str, str]:
    snaps = {}
    for fn in os.listdir(path):
        if fn.endswith(".html"):
            with open(os.path.join(path, fn), encoding="utf-8") as f:
                snaps[fn[:-5]] = f.read()
    return snaps


def collect(snaps: dict[str, str]) -> dict:
    if "all" not in snaps:
        raise ScrapeError("Немає знімка «Всі райони».")
    data = {"avg": parse_all(snaps["all"]), "rooms": {}, "changes": parse_changes(snaps["all"]),
            "meta": parse_meta(snaps["all"])}
    for d in DISTRICTS:
        if d not in snaps:
            raise ScrapeError(f"Немає знімка району «{d}».")
        data["rooms"][d] = parse_district(snaps[d], d)
    validate(data)
    if data["meta"]["rate"] is None:
        log.warning("Не вдалося прочитати курс DIM.RIA.")
    return data


# ── Аналітика й текст ──────────────────────────────────────────────────────────
def prev_key(key: str) -> str:
    y, m = map(int, key.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def pct(new: Optional[int], old: Optional[int]) -> Optional[float]:
    return (new / old - 1) * 100 if new and old else None


def analyze(data: dict, prev: Optional[dict]) -> dict:
    rows = []
    for d in DISTRICTS:
        r = data["rooms"][d]
        p = (prev or {}).get("rooms", {}).get(d) or {}
        pa = ((prev or {}).get("avg") or {}).get(d)
        rows.append({"name": d, "avg": data["avg"][d], "r1": r[1], "r2": r[2], "r3": r[3], "r4": r[4],
                     "dir": data["changes"].get(d), "mom1": pct(r[1], p.get("1")), "mom_avg": pct(data["avg"][d], pa)})
    rows.sort(key=lambda x: -x["r1"])
    lo, hi = min(rows, key=lambda x: x["r1"]), max(rows, key=lambda x: x["r1"])
    return {"rows": rows, "ratio": hi["r1"] / lo["r1"], "hi": hi, "lo": lo,
            "dirs": {k: [r["name"] for r in rows if r["dir"] == k] for k in ("up", "down", "same")},
            "meta": data["meta"], "has_prev": bool(prev)}


def fk(v: Optional[int]) -> str:
    """38284 → '38,3' (тис. грн)."""
    return "—" if v is None else f"{v / 1000:.1f}".replace(".", ",")


def fpct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return ("+" if v > 0.05 else "−" if v < -0.05 else "") + f"{abs(v):.1f}".replace(".", ",") + "%"


def asof_label(d: date) -> str:
    return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year}"


def build_text(a: dict, asof: date) -> str:
    e = lambda t: html.escape(t, quote=False)
    m = a["meta"]
    n = f"{m['listings']:,}".replace(",", "\u00a0") if m.get("listings") else ""
    sample = f", {n} активних оголошень" if n else ""
    L = ["🏠 <b>Оренда квартир у Києві: скільки це коштує на місяць</b>",
         f"📅 Станом на {asof_label(asof)} · дані <a href=\"{URL}\">DIM.RIA</a>{sample}", "",
         "Вартість оренди сильно залежить від району й від кількості кімнат, тому найчесніше порівнювати "
         "однакові квартири. Нижче — місячна оренда окремо для 1-, 2- і 3-кімнатних (тис. грн)."]
    L += ["", "📊 <b>Оренда за районами</b> <i>(тис. грн на місяць)</i>"]
    head = f"{'Район':<14} {'1-к':>5} {'2-к':>5} {'3-к':>5}" + (f" {'до мин.':>8}" if a["has_prev"] else "")
    body = [head]
    for r in a["rows"]:
        line = f"{r['name']:<14} {fk(r['r1']):>5} {fk(r['r2']):>5} {fk(r['r3']):>5}"
        if a["has_prev"]:
            line += f" {fpct(r['mom1']):>8}"
        body.append(line)
    L.append("<pre>" + e("\n".join(body)) + "</pre>")
    if a["has_prev"]:
        L.append("<i>Остання колонка — зміна ціни однокімнатної до попереднього місяця за нашими вимірами.</i>")

    hi, lo = a["hi"], a["lo"]
    L += ["", f"Найдорожча оренда однокімнатної — <b>{e(hi['name'])}</b> ({fk(hi['r1'])} тис. грн), "
              f"найдоступніша — <b>{e(lo['name'])}</b> ({fk(lo['r1'])} тис.): різниця у "
              f"{str(round(a['ratio'], 1)).replace('.', ',')} раза."]
    d = a["dirs"]
    if any(d.values()):
        L += ["", "📈 <b>Що відбувається за місяць</b> <i>(оцінка DIM.RIA за середньою ціною району)</i>"]
        if d["up"]:
            L.append("▲ Дорожчає: " + ", ".join(e(x) for x in d["up"]))
        if d["down"]:
            L.append("▼ Дешевшає: " + ", ".join(e(x) for x in d["down"]))
        if d["same"]:
            L.append("■ Без змін: " + ", ".join(e(x) for x in d["same"]))
    rate = f" Гривневі суми DIM.RIA розраховує за своїм курсом (1 $ ≈ {str(m['rate']).replace('.', ',')} грн)." if m.get("rate") else ""
    L += ["", "💡 <b>Як читати ці цифри?</b>",
          "Це ціни з оголошень, тобто ціни пропозиції: після торгу реальні договори можуть бути нижчими, "
          "а меблі, техніка й комунальні в оголошеннях враховані не завжди. У районах, де оголошень менше, "
          "ціни можуть «стрибати» від місяця до місяця." + rate,
          "", f"📌 Джерело: <a href=\"{URL}\">DIM.RIA</a>.", "", HASHTAGS]
    return "\n".join(L)


# ── Telegram, стан ─────────────────────────────────────────────────────────────
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


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict, key: str, data: dict) -> None:
    snaps = state.get("snapshots", {})
    snaps[key] = {"avg": data["avg"], "rooms": {d: {str(k): v for k, v in r.items()} for d, r in data["rooms"].items()},
                  "rate": data["meta"].get("rate")}
    state = {"last_period": key, "snapshots": dict(sorted(snaps.items())[-36:])}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


# ── main ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати й не зберігати стан")
    ap.add_argument("--debug", action="store_true", help="зберегти HTML-знімки у orenda_debug/")
    ap.add_argument("--from-dir", help="не відкривати браузер: узяти знімки (all.html, <район>.html) із каталогу")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    today = date.today() if args.from_dir else datetime.now(TZ).date()
    key = f"{today.year}-{today.month:02d}"
    state = load_state()
    force = args.force or os.getenv("FORCE_RUN") == "1"
    if not args.dry_run and not force and state.get("last_period") == key:
        log.info("За %s уже опубліковано — вихід.", key)
        return 0
    try:
        snaps = load_from_dir(args.from_dir) if args.from_dir else scrape_live(debug=args.debug)
        data = collect(snaps)
    except ScrapeError as e:
        log.error("Публікації не буде: %s", e)
        return 1

    prev = state.get("snapshots", {}).get(prev_key(key))
    a = analyze(data, prev)
    label = asof_label(today)
    render_main_card(a, label, CARD1)
    render_heat_card(a, label, CARD2)
    text = build_text(a, today)
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
    save_state(state, key, data)
    log.info("Опубліковано за %s.", key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
