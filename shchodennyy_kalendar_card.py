# -*- coding: utf-8 -*-
"""Генератор картки 1080×1350 для календаря каналу «Київський не гідрометцентр»."""
from __future__ import annotations
import argparse
import math
import os
import re
from datetime import date, datetime
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
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


def generate_card(info: dict, out_path: str = "output/shchodennyy_kalendar_kyiv.png") -> str:
    day: date = info["date"]
    top, bottom = PALETTES[day.month]
    image = gradient(top, bottom).convert("RGBA")
    draw = ImageDraw.Draw(image)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W-520, -220, W+160, 460), fill=(255, 255, 255, 28))
    gd.ellipse((-260, H-520, 360, H+120), fill=(255, 255, 255, 20))
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image)
    white, soft = (255, 255, 255, 255), (255, 255, 255, 195)
    pad = 70
    draw.text((pad, 62), "КИЇВСЬКИЙ НЕ ГІДРОМЕТЦЕНТР", font=font(True, 31), fill=white)
    draw.text((pad, 108), "ЩОДЕННИЙ КАЛЕНДАР", font=font(False, 26), fill=soft)
    draw.line((pad, 160, W-pad, 160), fill=(255, 255, 255, 90), width=2)
    day_font = font(True, 330)
    draw.text((pad-10, 150), str(day.day), font=day_font, fill=white)
    month_x = pad + draw.textlength(str(day.day), font=day_font) + 24
    draw.text((month_x, 300), MONTHS_UPPER[day.month-1], font=font(True, 52), fill=white)
    draw.text((month_x, 372), info["weekday"].upper(), font=font(False, 39), fill=soft)
    draw.text((month_x, 424), str(day.year), font=font(False, 34), fill=soft)

    panel_y = 520
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((pad, panel_y, W-pad, panel_y+210), 36, fill=(0, 0, 0, 72))
    image = Image.alpha_composite(image, panel)
    draw = ImageDraw.Draw(image)
    moon = info["moon"]
    image.alpha_composite(moon_icon(moon["frac"], 150), (pad+36, panel_y+30))
    tx = pad + 36 + 150 + 34
    for i, line in enumerate(wrap(draw, moon["name"], font(True, 34), W-pad-tx-30)[:2]):
        draw.text((tx, panel_y+28+i*42), line, font=font(True, 34), fill=white)
    event = moon["event"]
    event_text = f"близько {event['time']} · " if event else ""
    draw.text((tx, panel_y+118), f"{event_text}освітлено ≈ {round(moon['illum']*100)}%", font=font(False, 27), fill=soft)
    sun = info["sun"]
    draw.text((tx, panel_y+160), f"Схід {sun['sunrise']} · Захід {sun['sunset']}", font=font(False, 27), fill=soft)

    y = panel_y + 260
    items = [("state", text) for text, _ in info["state"]] + [("church", text) for text, _ in info["church"]]
    if info["names"]:
        items.append(("names", "Іменини: " + info["names"]))
    text_font = font(False, 34)
    bottom_limit = H - 230
    shown = 0
    max_width = W - 2*pad - 60
    for kind, text in items:
        lines = wrap(draw, text, text_font, max_width)
        needed = len(lines)*44 + 16
        if y + needed > bottom_limit:
            break
        if kind == "state":
            draw.ellipse((pad+4, y+12, pad+22, y+30), fill=(255, 214, 102, 255))
        elif kind == "church":
            draw.rectangle((pad+10, y+8, pad+15, y+34), fill=(255, 255, 255, 235))
            draw.rectangle((pad+1, y+17, pad+24, y+22), fill=(255, 255, 255, 235))
        else:
            draw.polygon([(pad+13,y+6),(pad+18,y+18),(pad+31,y+18),(pad+21,y+26),(pad+25,y+38),(pad+13,y+31),(pad+1,y+38),(pad+5,y+26),(pad-5,y+18),(pad+8,y+18)], fill=(255,190,220,255))
        for line in lines:
            draw.text((pad+60, y), line, font=text_font, fill=white)
            y += 44
        y += 16
        shown += 1
    if shown < len(items):
        draw.text((pad+60, min(y, bottom_limit)), f"…і ще {len(items)-shown} — у тексті допису", font=font(False, 28), fill=soft)
    elif not items:
        draw.text((pad, y), "День для добрих справ і нових відкриттів", font=font(False, 32), fill=soft)

    draw = ImageDraw.Draw(image)
    draw.line((pad, H-150, W-pad, H-150), fill=(255,255,255,90), width=2)
    draw.text((pad, H-120), "t.me/kyyivskyy_ne_hidromettsentr", font=font(True, 27), fill=white)
    draw.text((pad, H-72), "Погода · календар · історії неба", font=font(False, 27), fill=soft)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    from zoneinfo import ZoneInfo
    from shchodennyy_kalendar import build_day
    parser = argparse.ArgumentParser(description="Створити картку календаря для Києва")
    parser.add_argument("--date", help="Дата РРРР-ММ-ДД; за замовчуванням — сьогодні за Києвом")
    parser.add_argument("--out", default="output/shchodennyy_kalendar_kyiv.png")
    args = parser.parse_args()
    today = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Europe/Kyiv")).date()
    print("Збережено:", generate_card(build_day(today), args.out))
