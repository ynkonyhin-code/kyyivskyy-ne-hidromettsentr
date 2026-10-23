# -*- coding: utf-8 -*-
"""Горизонтальна картка 1280×720 (16:9) для рубрики «Щоденний календар» —
«Київський не гідрометцентр» (https://t.me/kyyivskyy_ne_hidromettsentr).

Картка йде у Telegram разом із повним текстом у підписі, тому в каналі виходить одне повідомлення.
У шапці — аватар Котика-чергового (kotyk_avatar.png у корені репозиторію; якщо файлу немає — картка без нього).

Використання:
    python shchodennyy_kalendar_card.py                    # картка на сьогодні
    python shchodennyy_kalendar_card.py --date 2026-12-25 --out xmas.png
"""
from __future__ import annotations

import argparse
import math
import os
import re
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
AVATAR = os.path.join(HERE, "kotyk_avatar.png")

W, H = 1280, 720
PAD = 58
BOTTOM = 640                      # нижня межа вмісту (далі — лінія підвалу)

# Градієнти за місяцями: (верх, низ)
PALETTES = {
    1: ((18, 32, 66), (52, 90, 140)), 2: ((26, 40, 80), (84, 120, 170)),
    3: ((38, 78, 98), (120, 170, 160)), 4: ((34, 94, 98), (140, 198, 150)),
    5: ((30, 100, 80), (170, 214, 130)), 6: ((20, 110, 120), (240, 200, 110)),
    7: ((16, 100, 130), (250, 190, 90)), 8: ((24, 90, 120), (245, 170, 85)),
    9: ((90, 70, 40), (230, 160, 70)), 10: ((84, 44, 34), (206, 120, 60)),
    11: ((50, 52, 70), (130, 130, 150)), 12: ((14, 26, 58), (60, 100, 150)),
}
MONTHS_UPPER = ["СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ",
                "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ"]
FONT_DIRS = ["fonts", os.path.join(HERE, "fonts"),
             "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
             "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/noto",
             "/Library/Fonts", "/System/Library/Fonts/Supplemental", "C:/Windows/Fonts"]
REGULAR_FONTS = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "Arial.ttf", "arial.ttf"]
BOLD_FONTS = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200d]+")

_font_cache: dict = {}


def font(bold: bool, size: int):
    key = (bold, size)
    if key not in _font_cache:
        for folder in FONT_DIRS:
            for name in (BOLD_FONTS if bold else REGULAR_FONTS):
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    _font_cache[key] = ImageFont.truetype(path, size)
                    break
            if key in _font_cache:
                break
        else:
            raise RuntimeError("Не знайдено шрифт із кирилицею. У GitHub Actions встановлюється DejaVu Sans.")
    return _font_cache[key]


def fit_font(draw, text: str, bold: bool, size: int, max_w: int, min_size: int = 14):
    """Зменшує шрифт, доки текст не влізе у задану ширину (щоб нічого не вилазило за панель)."""
    while size > min_size and draw.textlength(text, font=font(bold, size)) > max_w:
        size -= 1
    return font(bold, size)


def gradient(top, bottom):
    image = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(image)
    for y in range(H):
        t = y / (H - 1)
        draw.line((0, y, W, y), fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return image


def clean(text: str) -> str:
    """Шрифт не має емодзі — прибираємо їх лише з картки (у тексті поста вони лишаються)."""
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", str(text))).strip()


def wrap(draw, text, selected_font, max_width):
    words, lines, current = clean(text).split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=selected_font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def clip_lines(lines: list[str], limit: int) -> list[str]:
    """Обрізає список рядків до limit; на останньому рядку ставить «…»."""
    if len(lines) <= limit:
        return lines
    out = lines[:limit]
    out[-1] = out[-1].rstrip(" ,.;:—-") + "…"
    return out


def moon_icon(frac: float, size: int) -> Image.Image:
    """Місяць за часткою циклу (0=новий, 0.5=повня). Північна пів­куля: молодий — справа."""
    scale = 3
    side = size * scale
    icon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    radius = side / 2 - 4 * scale
    cx = cy = side / 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill=(38, 46, 70, 255), outline=(255, 255, 255, 90), width=2 * scale)
    k = math.cos(2 * math.pi * frac)
    for y in range(int(cy - radius), int(cy + radius) + 1):
        dy = y - cy
        if abs(dy) > radius:
            continue
        width = math.sqrt(max(radius * radius - dy * dy, 0))
        x0, x1 = (cx + width * k, cx + width) if frac <= 0.5 else (cx - width, cx - width * k)
        if x1 - x0 > 0.5:
            draw.line((x0, y, x1, y), fill=(250, 244, 220, 255), width=1)
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def kotyk_badge(size: int):
    """Круглий аватар Котика-чергового з тонким світлим обідком; None, якщо файлу немає."""
    try:
        av = Image.open(AVATAR).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    except (FileNotFoundError, OSError):
        return None
    scale = 4
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    badge.paste(av, (0, 0), mask)
    ring = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, size * scale - 1, size * scale - 1), outline=(255, 255, 255, 235), width=3 * scale)
    badge.alpha_composite(ring.resize((size, size), Image.Resampling.LANCZOS))
    return badge


def draw_bullet(draw, x, y, kind):
    if kind == "state":
        draw.ellipse((x, y + 7, x + 13, y + 20), fill=(255, 214, 102, 255))
    elif kind == "church":
        draw.rectangle((x + 5, y + 2, x + 9, y + 24), fill=(255, 255, 255, 235))
        draw.rectangle((x - 1, y + 9, x + 15, y + 13), fill=(255, 255, 255, 235))
    else:
        draw.ellipse((x + 1, y + 4, x + 14, y + 17), outline=(255, 190, 220, 255), width=3)


def generate_card(info: dict, out_path: str = "output/shchodennyy_kalendar_kyiv.png") -> str:
    day: date = info["date"]
    top, bottom = PALETTES[day.month]
    image = gradient(top, bottom).convert("RGBA")

    # М'яке декоративне світло — достатній контраст для білого тексту.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W - 360, -185, W + 130, 300), fill=(255, 255, 255, 25))
    gd.ellipse((-220, H - 250, 320, H + 130), fill=(255, 255, 255, 18))
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image)
    white, soft, gold = (255, 255, 255, 255), (255, 255, 255, 205), (255, 224, 153, 255)

    # ── Шапка: аватар Котика + назва каналу ────────────────────────────────
    badge = kotyk_badge(80)
    text_x = PAD
    if badge:
        image.alpha_composite(badge, (PAD, 16))
        text_x = PAD + 98
    draw.text((text_x, 24), "КИЇВСЬКИЙ НЕ ГІДРОМЕТЦЕНТР", font=font(True, 29), fill=white)
    draw.text((text_x, 66), "ЩОДЕННИЙ КАЛЕНДАР", font=font(False, 21), fill=soft)
    draw.line((PAD, 112, W - PAD, 112), fill=(255, 255, 255, 90), width=2)

    # ── Дата ─────────────────────────────────────────────────────────────────
    day_font = font(True, 205)
    day_text = str(day.day)
    draw.text((PAD - 5, 126), day_text, font=day_font, fill=white)
    day_width = draw.textlength(day_text, font=day_font)
    month_x = int(PAD + day_width + 20)
    draw.text((month_x, 194), MONTHS_UPPER[day.month - 1], font=fit_font(draw, MONTHS_UPPER[day.month - 1], True, 37, 600 - month_x), fill=white)
    draw.text((month_x, 240), info["weekday"].upper(), font=font(False, 27), fill=soft)
    draw.text((month_x, 279), str(day.year), font=font(False, 26), fill=soft)
    draw.text((PAD + 2, 345), "КИЇВ · УКРАЇНА", font=font(True, 17), fill=soft)

    # ── Панель: Місяць і Сонце ───────────────────────────────────────────────
    panel_box = (625, 135, W - PAD, 380)
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(panel_box, 28, fill=(0, 0, 0, 72), outline=(255, 255, 255, 32), width=1)
    image = Image.alpha_composite(image, panel)
    draw = ImageDraw.Draw(image)
    moon = info["moon"]
    image.alpha_composite(moon_icon(moon["frac"], 132), (650, 175))
    tx = 808
    inner_w = panel_box[2] - 24 - tx                       # доступна ширина тексту в панелі
    moon_font = font(True, 30)
    name_lines = clip_lines(wrap(draw, moon["name"], moon_font, inner_w), 2)
    event = moon["event"]
    phase_line = (f"о {event['time']} · " if event else "") + f"освітлено ≈ {round(moon['illum'] * 100)}%"
    sun = info["sun"]
    sun_line = f"Схід {sun['sunrise']}  ·  Захід {sun['sunset']}"
    len_line = f"Тривалість дня: {sun['day_len']}"
    block_h = len(name_lines) * 38 + 12 + 41 * 2 + 26       # висота тексту — центруємо у панелі
    y0 = (panel_box[1] + panel_box[3]) // 2 - block_h // 2
    for i, line in enumerate(name_lines):
        draw.text((tx, y0 + i * 38), line, font=moon_font, fill=white)
    py = y0 + len(name_lines) * 38 + 12
    draw.text((tx, py), phase_line, font=fit_font(draw, phase_line, False, 21, inner_w), fill=soft)
    draw.text((tx, py + 41), sun_line, font=fit_font(draw, sun_line, True, 22, inner_w), fill=white)
    draw.text((tx, py + 82), len_line, font=fit_font(draw, len_line, False, 21, inner_w), fill=soft)

    # ── Нижня частина: події ліворуч, легенда й прикмета праворуч ───────────
    draw.line((PAD, 405, W - PAD, 405), fill=(255, 255, 255, 78), width=2)
    draw.line((630, 425, 630, BOTTOM - 6), fill=(255, 255, 255, 70), width=2)
    section_font = font(True, 20)
    draw.text((PAD, 421), "СЬОГОДНІ", font=section_font, fill=gold)
    draw.text((665, 421), "ЛЕГЕНДА ДНЯ", font=section_font, fill=gold)

    items = [("state", text) for text, _ in info["state"]]
    items += [("church", text) for text, _ in info["church"]]
    if info.get("names"):
        items.append(("names", "Іменини: " + info["names"]))
    event_font = font(False, 22)
    left_w = 515
    y = 456
    max_lines = 5                                          # скільки рядків вміщається ліворуч
    used = shown = 0
    for kind, text in items:
        lines = wrap(draw, text, event_font, left_w)
        room = max_lines - used
        if room <= 0 or (len(lines) > room and shown > 0):
            break
        lines = clip_lines(lines, room)
        draw_bullet(draw, PAD + 2, y + 1, kind)
        for line in lines:
            draw.text((PAD + 27, y), line, font=event_font, fill=white)
            y += 27
        y += 5
        used += len(lines)
        shown += 1
    if len(items) > shown:
        draw.text((PAD + 27, min(y, BOTTOM - 22)), "…ще події та іменини — в описі", font=font(False, 19), fill=soft)
    elif not items:
        draw.text((PAD + 3, 460), "День для добрих справ і нових відкриттів", font=font(False, 22), fill=white)

    title, story = info["legend"]
    ry = 455
    title_font = font(True, 25)
    for line in clip_lines(wrap(draw, title, title_font, 545), 2):
        draw.text((665, ry), line, font=title_font, fill=white)
        ry += 31
    ry += 8
    story_font = font(False, 18)
    sign_font = font(False, 17)
    sign_lines = clip_lines(wrap(draw, "Прикмета: " + info["prykmeta"], sign_font, 548), 2)
    sign_h = len(sign_lines) * 20
    story_room = max(1, (BOTTOM - 10 - sign_h - 14 - ry) // 22)   # скільки рядків легенди лишається
    story_lines = clip_lines(wrap(draw, story, story_font, 548), min(4, story_room))
    for line in story_lines:
        draw.text((665, ry), line, font=story_font, fill=soft)
        ry += 22
    ry += 14
    for line in sign_lines:
        draw.text((665, ry), line, font=sign_font, fill=white)
        ry += 20

    # ── Підвал ───────────────────────────────────────────────────────────────
    draw.line((PAD, 655, W - PAD, 655), fill=(255, 255, 255, 78), width=2)
    draw.text((PAD, 668), "t.me/kyyivskyy_ne_hidromettsentr", font=font(True, 19), fill=white)
    tag = "ПОГОДА · КАЛЕНДАР · ІСТОРІЇ НЕБА"
    tag_font = font(False, 17)
    draw.text((W - PAD - draw.textlength(tag, font=tag_font), 670), tag, font=tag_font, fill=soft)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    from zoneinfo import ZoneInfo
    from shchodennyy_kalendar import build_day
    parser = argparse.ArgumentParser(description="Створити горизонтальну картку календаря для Києва")
    parser.add_argument("--date", help="Дата РРРР-ММ-ДД; за замовчуванням — сьогодні за Києвом")
    parser.add_argument("--out", default="output/shchodennyy_kalendar_kyiv.png")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Europe/Kyiv")).date()
    print("Збережено:", generate_card(build_day(today), args.out))
