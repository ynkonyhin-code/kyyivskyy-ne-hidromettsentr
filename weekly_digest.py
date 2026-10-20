# ФАЙЛ: weekly_digest.py | ЗАДАЧА: «Підсумок тижня» (щопонеділка) | КУДИ: корінь репозиторію
# ПАРА: .github/workflows/weekly_digest.yml + events_db.py (+ weather_journal.py наповнює погоду в журналі)
"""Публікація недільного підсумку в канал «Київський не гідрометцентр».

    python weekly_digest.py          # відправити в канал
    python weekly_digest.py --dry    # лише показати текст, нічого не відправляти
Змінні середовища: TELEGRAM_BOT_TOKEN, CHAT_ID
"""
import os
import sys

import requests

from events_db import weekly_digest

# Хештеги поста: змінюйте як подобається
TAGS = "#Київ #КиївськийНеГідрометцентр #Погода #ПідсумокТижня"


def main():
    text = weekly_digest() + "\n\n" + TAGS
    if "--dry" in sys.argv:
        print(text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        data={"chat_id": os.environ["CHAT_ID"], "text": text, "parse_mode": "HTML"},
        timeout=30)
    r.raise_for_status()


if __name__ == "__main__":
    main()
