#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ФАЙЛ: weather_journal.py | ЗАДАЧА: щодня записує ФАКТИЧНУ погоду Києва за минулу добу в journal/weather/<дата>.json
# КУДИ: корінь репозиторію | ПАРА: .github/workflows/weather_journal.yml + events_db.py
"""Журнал погоди для «Підсумку тижня».

Бере з Open-Meteo (безкоштовно, без ключа) підсумки за минулі дні для Києва і зберігає
[темп. макс., темп. мін., опади мм, вітер макс. м/с] у journal/weather/<дата>.json.
Вчорашня доба перезаписується завжди (дані остаточні), давніші дні дописуються лише якщо їх
ще немає — тому при першому запуску журнал одразу заповниться за тиждень.

Запуск:   python weather_journal.py            # записати і (у GitHub Actions) зберегти в git
          DRY_RUN=1 python weather_journal.py  # лише показати, що було б записано
Змінні:   DRY_RUN=1
"""
import os
import sys
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from events_db import JOURNAL_DIR, commit_journal, save_daily_weather

LAT, LON = 50.4501, 30.5234          # Київ
TZ = ZoneInfo("Europe/Kyiv")
API = "https://api.open-meteo.com/v1/forecast"
DRY_RUN = os.getenv("DRY_RUN", "").strip() == "1"


def fetch() -> dict:
    params = {"latitude": LAT, "longitude": LON, "timezone": "Europe/Kyiv", "wind_speed_unit": "ms",
              "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
              "past_days": 7, "forecast_days": 1}
    last = None
    for i in range(4):
        try:
            r = requests.get(API, params=params, timeout=25)
            r.raise_for_status()
            return r.json()["daily"]
        except (requests.RequestException, ValueError, KeyError) as e:
            last = e
            print(f"Open-Meteo не відповів (спроба {i + 1}/4): {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Не вдалося отримати погоду: {last}")


def main() -> int:
    today = datetime.now(TZ).date()
    d = fetch()
    saved = 0
    for i, day_s in enumerate(d["time"]):
        day = date.fromisoformat(day_s)
        if day >= today:                                   # сьогодні ще не закінчилось
            continue
        is_yesterday = (today - day).days == 1
        if (JOURNAL_DIR / "weather" / f"{day_s}.json").exists() and not is_yesterday:
            continue
        vals = [d["temperature_2m_max"][i], d["temperature_2m_min"][i],
                d["precipitation_sum"][i], d["wind_speed_10m_max"][i]]
        if vals[0] is None or vals[1] is None:
            print(f"{day_s}: даних немає, пропускаю")
            continue
        vals = [None if v is None else round(v, 1) for v in vals]
        print(f"{day_s}: макс {vals[0]}°, мін {vals[1]}°, опади {vals[2]} мм, вітер до {vals[3]} м/с")
        if not DRY_RUN:
            save_daily_weather(day_s, *vals)
        saved += 1
    if DRY_RUN:
        print(f"[DRY RUN] було б записано днів: {saved}")
        return 0
    commit_journal()
    print(f"Записано днів: {saved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
