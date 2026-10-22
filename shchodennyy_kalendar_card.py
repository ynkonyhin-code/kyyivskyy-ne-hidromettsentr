# -*- coding: utf-8 -*-
"""Горизонтальна картка 1280×720 (16:9) для рубрики «Щоденний календар».

Картка розрахована на стандартну ширину Telegram-публікації. Повний календарний
текст передається в caption фотографії, тому в каналі виходить одне повідомлення.
"""
from __future__ import annotations
import argparse
import math
import os
import re
from datetime import date, datetime
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
PAD = 58
PALETTES = {
    1: ((18, 32, 66), (52, 90, 140)), 2: ((26, 40, 80), (84, 120, 170)),
    3: ((38, 78, 98), (120, 170, 160)), 4: ((34, 94, 98), (140, 198, 150)),
    5: ((30, 100, 80), (170, 214, 130)), 6: ((20, 110, 120), (240, 200, 110)),
    7: ((16, 100, 130), (250, 190, 90)), 8: ((24, 90, 120), (245, 170, 85)),
    9: ((90, 70, 40), (230, 160, 70)), 10: ((84, 44, 34), (206, 120, 60)),
    11: ((50, 52, 70), (130, 130, 150)), 12: ((14, 26, 58), (60, 100, 150)),
}
MONTHS_UPPER = ["СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ", "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ"]
FONT_DIRS = ["fonts", "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/noto", "/Library/Fonts", "C:/Windows/Fonts"]
REGULAR_FONTS = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "Arial.ttf", "arial.ttf"]
BOLD_FONTS = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200d]+")


def font(bold: bool, size: int):
    for folder in FONT_DIRS:
        for name in (BOLD_FONTS if bold else REGULAR_FONTS):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)
    raise RuntimeError("Не знайдено шрифт із кирилицею. У GitHub Actions встановлюється DejaVu Sans.")


def gradient(top, bottom):
    image = Image.new("RGB", (W, H), top)
    draw = ImageDraw.Draw(image)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line((0, y, W, y), fill=color)
    return image


def clean(text: str) -> str:
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


def moon_icon(frac: float, size: int) -> Image.Image:
    scale = 3
    side = size * scale
    icon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    radius = side / 2 - 4 * scale
    cx = cy = side / 2
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=(38, 46, 70, 255), outline=(255, 255, 255, 90), width=2*scale)
    k = math.cos(2 * math.pi * frac)
    for y in range(int(cy-radius), int(cy+radius)+1):
        dy = y-cy
        if abs(dy) > radius:
            continue
        width = math.sqrt(max(radius*radius-dy*dy, 0))
        x0, x1 = (cx + width*k, cx + width) if frac <= 0.5 else (cx-width, cx-width*k)
        if x1-x0 > 0.5:
            draw.line((x0, y, x1, y), fill=(250, 244, 220, 255), width=1)
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def draw_bullet(draw, x, y, kind):
    if kind == "state":
        draw.ellipse((x, y+7, x+13, y+20), fill=(255, 214, 102, 255))
    elif kind == "church":
        draw.rectangle((x+5, y+2, x+9, y+24), fill=(255, 255, 255, 235))
        draw.rectangle((x-1, y+9, x+15, y+13), fill=(255, 255, 255, 235))
    else:
        draw.ellipse((x+1, y+4, x+14, y+17), outline=(255, 190, 220, 255), width=3)


def generate_card(info: dict, out_path: str = "output/shchodennyy_kalendar_kyiv.png") -> str:
    day: date = info["date"]
    top, bottom = PALETTES[day.month]
    image = gradient(top, bottom).convert("RGBA")

    # Soft decorative light, with enough contrast for white text.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W-360, -185, W+130, 300), fill=(255, 255, 255, 25))
    gd.ellipse((-220, H-250, 320, H+130), fill=(255, 255, 255, 18))
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image)
    white, soft = (255, 255, 255, 255), (255, 255, 255, 198)

    # Header
    draw.text((PAD, 32), "КИЇВСЬКИЙ НЕ ГІДРОМЕТЦЕНТР", font=font(True, 29), fill=white)
    draw.text((PAD, 72), "ЩОДЕННИЙ КАЛЕНДАР", font=font(False, 21), fill=soft)
    draw.line((PAD, 112, W-PAD, 112), fill=(255, 255, 255, 90), width=2)

    # Date block — arranged horizontally for the 16:9 format.
    day_font = font(True, 205)
    day_text = str(day.day)
    draw.text((PAD-5, 126), day_text, font=day_font, fill=white)
    day_width = draw.textlength(day_text, font=day_font)
    month_x = int(PAD + day_width + 20)
    month_font = font(True, 37)
    draw.text((month_x, 194), MONTHS_UPPER[day.month-1], font=month_font, fill=white)
    draw.text((month_x, 240), info["weekday"].upper(), font=font(False, 27), fill=soft)
    draw.text((month_x, 279), str(day.year), font=font(False, 26), fill=soft)
    draw.text((PAD+2, 345), "КИЇВ · УКРАЇНА", font=font(True, 17), fill=soft)

    # Moon and solar times in a wide panel.
    panel_box = (625, 135, W-PAD, 380)
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(panel_box, 28, fill=(0, 0, 0, 72), outline=(255,255,255,32), width=1)
    image = Image.alpha_composite(image, panel)
    draw = ImageDraw.Draw(image)
    moon = info["moon"]
    image.alpha_composite(moon_icon(moon["frac"], 132), (650, 175))
    tx = 808
    moon_font = font(True, 30)
    moon_lines = wrap(draw, moon["name"], moon_font, W-PAD-tx-28)
    for i, line in enumerate(moon_lines[:2]):
        draw.text((tx, 170+i*38), line, font=moon_font, fill=white)
    event = moon["event"]
    event_text = f"Фаза близько {event['time']} · " if event else ""
    draw.text((tx, 254), f"{event_text}освітлено ≈ {round(moon['illum']*100)}%", font=font(False, 21), fill=soft)
    sun = info["sun"]
    draw.text((tx, 295), f"Схід {sun['sunrise']}  ·  Захід {sun['sunset']}", font=font(True, 22), fill=white)
    draw.text((tx, 335), f"Тривалість дня: {sun['day_len']}", font=font(False, 21), fill=soft)

    # Lower half: compact key events on the left, legend and folk sign on the right.
    draw.line((PAD, 405, W-PAD, 405), fill=(255,255,255,78), width=2)
    draw.line((630, 425, 630, 632), fill=(255,255,255,70), width=2)
    section_font = font(True, 20)
    draw.text((PAD, 421), "СЬОГОДНІ", font=section_font, fill=(255, 224, 153, 255))
    draw.text((665, 421), "ЛЕГЕНДА ДНЯ", font=section_font, fill=(255, 224, 153, 255))

    items = [("state", text) for text, _ in info["state"]]
    items += [("church", text) for text, _ in info["church"]]
    if info.get("names"):
        items.append(("names", "Іменини: " + info["names"]))
    event_font = font(False, 22)
    y = 456
    shown = 0
    shown_items = 0
    max_event_lines = 4
    for kind, text in items:
        lines = wrap(draw, text, event_font, 500)
        if shown + len(lines) > max_event_lines:
            break
        draw_bullet(draw, PAD+2, y+1, kind)
        for line in lines:
            draw.text((PAD+27, y), line, font=event_font, fill=white)
            y += 27
        y += 5
        shown += len(lines)
        shown_items += 1
    if len(items) > shown_items:
        draw.text((PAD+27, min(y, 603)), f"…ще події та іменини — в описі", font=font(False, 19), fill=soft)
    elif not items:
        draw.text((PAD+3, 460), "День для добрих справ і нових відкриттів", font=font(False, 21), fill=white)

    title, story = info["legend"]
    legend_title_font = font(True, 25)
    title_lines = wrap(draw, title, legend_title_font, 545)
    for i, line in enumerate(title_lines[:2]):
        draw.text((665, 455+i*31), line, font=legend_title_font, fill=white)
    story_y = 510 if len(title_lines) <= 1 else 520
    story_font = font(False, 18)
    story_lines = wrap(draw, story, story_font, 548)
    for i, line in enumerate(story_lines[:3]):
        draw.text((665, story_y+i*22), line, font=story_font, fill=soft)
    sign_y = 584 if len(story_lines) <= 2 else 606
    sign_font = font(False, 17)
    sign = wrap(draw, "Прикмета: " + info["prykmeta"], sign_font, 548)
    for i, line in enumerate(sign[:2]):
        draw.text((665, sign_y+i*20), line, font=sign_font, fill=white)

    # Footer branding
    draw.line((PAD, 655, W-PAD, 655), fill=(255,255,255,78), width=2)
    draw.text((PAD, 668), "t.me/kyyivskyy_ne_hidromettsentr", font=font(True, 19), fill=white)
    draw.text((720, 668), "ПОГОДА · КАЛЕНДАР · ІСТОРІЇ НЕБА", font=font(False, 17), fill=soft)

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
