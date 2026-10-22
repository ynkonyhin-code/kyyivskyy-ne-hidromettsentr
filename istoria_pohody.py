#!/usr/bin/env python3
"""
istoria_pohody — рубрика «Погода, що змінила історію» для «Київського не гідрометцентру».
Одна історія за випуск: що сталося, що змінилося, застереження істориків і джерела.
Виходить раз на тиждень — у четвер, о 17:30 + випадкові 0–45 хв за Києвом.
Історії йдуть по порядку; після останньої починається коло знову (нові додавайте в istoria_pohody_data.py).
Потрібні змінні середовища: TELEGRAM_BOT_TOKEN (або BOT_TOKEN), CHAT_ID.
Необов'язково: TEST_POST=true (надіслати наступний випуск зараз, без збереження стану).
Запуск без відправки: python istoria_pohody.py --dry-run [--index N]
"""
import html
import json
import os
import random
import sys
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

import requests

from istoria_pohody_data import IST

KYIV = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "istoria_pohody_state.json")
WEEKDAYS = {3}                   # четвер (0 = понеділок)
BASE, SPREAD_MIN, LATEST = (17, 30), 45, (19, 0)
BASE_TAGS = "#ПогодаЩоЗмінилаІсторію #історія #погода #КиївськийНеГідрометцентр #Київ"


def esc(s):
    return html.escape(s, quote=False)


def build_post(idx, issue_no):
    h = IST[idx % len(IST)]
    nxt = IST[(idx + 1) % len(IST)]
    lines = [
        "🌪 <b>ПОГОДА, ЩО ЗМІНИЛА ІСТОРІЮ</b>",
        f"<i>Історія №{issue_no}</i>",
        "",
        f"📅 <b>{esc(h['year'])} · {esc(h['title'])}</b>",
        "",
        esc(h["story"]),
        "",
        f"🧭 <b>Що змінилося.</b> {esc(h['changed'])}",
    ]
    if h.get("note"):
        lines += ["", f"💬 <i>{esc(h['note'])}</i>"]
    lines += [
        "",
        f"🔜 <b>Наступного разу:</b> {esc(nxt['year'])} · {esc(nxt['title'])}",
        "",
        f"📚 <i>Джерела: {esc(h['source'])}</i>",
        "",
        f"{BASE_TAGS} {h['tag']}",
    ]
    return "\n".join(lines)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    dry = "--dry-run" in sys.argv
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    state = load_state()
    if dry:
        idx = int(sys.argv[sys.argv.index("--index") + 1]) if "--index" in sys.argv else state.get("next_index", 0)
        text = build_post(idx % len(IST), state.get("issue_no", 0) + 1)
        print(text)
        print(f"\n[dry-run] символів: {len(text)} із 4096")
        return 0 if len(text) <= 4096 else 1
    if not token or not chat_id:
        print("[error] TELEGRAM_BOT_TOKEN / CHAT_ID не задані")
        return 1

    test = os.environ.get("TEST_POST", "").lower() == "true"
    now = datetime.now(KYIV)
    today = now.date().isoformat()
    if not test:
        if now.weekday() not in WEEKDAYS:
            print("[skip] сьогодні не день цієї рубрики")
            return 0
        if state.get("last_date") == today:
            print("[skip] сьогодні вже опубліковано")
            return 0
        base = now.replace(hour=BASE[0], minute=BASE[1], second=0, microsecond=0)
        target = base + timedelta(minutes=random.Random(f"istoria-{today}").randint(0, SPREAD_MIN))
        if now < target:
            print(f"[wait] сьогоднішній час публікації — {target:%H:%M} (Київ)")
            return 0
        if now > now.replace(hour=LATEST[0], minute=LATEST[1], second=0, microsecond=0):
            print("[skip] занадто пізно для цієї рубрики")
            return 0

    idx = state.get("next_index", 0) % len(IST)
    issue_no = state.get("issue_no", 0) + 1
    text = build_post(idx, issue_no)
    if len(text) > 4096:
        print(f"[error] пост задовгий: {len(text)} символів")
        return 1
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"[error] Telegram: {r.status_code} {r.text}")
        return 1
    print(f"[ok] опубліковано історію №{issue_no}: {IST[idx]['title']}")
    if not test:
        state.update(last_date=today, next_index=(idx + 1) % len(IST), issue_no=issue_no)
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
