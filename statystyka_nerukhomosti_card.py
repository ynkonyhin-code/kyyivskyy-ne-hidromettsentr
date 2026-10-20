from PIL import Image, ImageDraw, ImageFont
import os
import math
import re


WIDTH, HEIGHT = 1200, 675
OUTPUT_DEFAULT = "realty_card.jpg"


def _font(size, bold=False):
    """Знаходить шрифт із підтримкою української кирилиці на GitHub Actions/Linux."""
    candidates = []
    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "arialbd.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "arial.ttf",
        ])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _gradient_background():
    """Створює стилізований вечірній силует Києва, Дніпра й мосту."""
    image = Image.new("RGB", (WIDTH, HEIGHT))
    px = image.load()
    top = (8, 19, 42)
    bottom = (18, 48, 76)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(WIDTH):
            px[x, y] = color

    draw = ImageDraw.Draw(image, "RGBA")

    # М'яке сяйво над горизонтом.
    for radius in range(260, 0, -8):
        alpha = max(1, int(9 * (1 - radius / 270)))
        draw.ellipse(
            (850 - radius, 185 - radius, 850 + radius, 185 + radius),
            fill=(58, 157, 197, alpha),
        )

    # Далекий берег і силует міста.
    draw.polygon(
        [(0, 300), (80, 278), (135, 298), (190, 250), (235, 285),
         (285, 263), (340, 300), (410, 270), (475, 305), (545, 265),
         (620, 300), (700, 275), (780, 303), (850, 260), (930, 290),
         (1010, 250), (1080, 285), (1200, 260), (1200, 675), (0, 675)],
        fill=(12, 34, 57, 210),
    )

    # Будинки з вікнами.
    buildings = [
        (15, 340, 75, 475), (82, 315, 145, 485), (155, 365, 205, 500),
        (218, 325, 278, 470), (292, 350, 355, 500), (370, 305, 425, 475),
        (438, 360, 490, 500), (500, 325, 565, 490), (580, 350, 640, 495),
        (650, 315, 710, 480), (720, 355, 780, 500), (790, 330, 850, 485),
        (865, 355, 925, 505), (940, 315, 1000, 480), (1015, 345, 1080, 500),
        (1090, 320, 1160, 485),
    ]
    for x1, y1, x2, y2 in buildings:
        draw.rectangle((x1, y1, x2, y2), fill=(15, 42, 66, 220),
                       outline=(67, 123, 151, 75), width=1)
        for wy in range(y1 + 14, y2 - 8, 22):
            for wx in range(x1 + 10, x2 - 6, 17):
                if (wx + wy) % 4:
                    draw.rectangle((wx, wy, wx + 4, wy + 7),
                                   fill=(246, 190, 95, 95))

    # Лівобережні дахи, лінія води та міст.
    draw.polygon([(0, 505), (200, 488), (390, 510), (560, 485),
                  (760, 515), (960, 492), (1200, 510), (1200, 675), (0, 675)],
                 fill=(7, 25, 45, 235))
    draw.line([(0, 535), (1200, 535)], fill=(88, 174, 202, 90), width=2)
    draw.line([(0, 560), (1200, 560)], fill=(88, 174, 202, 45), width=1)
    draw.line([(0, 585), (1200, 585)], fill=(88, 174, 202, 30), width=1)
    draw.line([(0, 510), (180, 500), (350, 518), (520, 502),
               (700, 518), (890, 503), (1050, 515), (1200, 504)],
              fill=(78, 171, 205, 140), width=3)

    # Темний шар забезпечує контраст тексту незалежно від фону.
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (3, 12, 28, 100))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    return image


def _price_number(value):
    try:
        return float(re.sub(r"[^\d.,]", "", str(value)).replace(",", "."))
    except (TypeError, ValueError):
        return -1


def _fit_text(draw, text, font, max_width):
    """Обрізає надто довгі підписи без виходу за межі картки."""
    text = str(text)
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-2].rstrip() + "…"
    return text


def generate_real_estate_card(data_dict, month_str, output_path=OUTPUT_DEFAULT):
    """Генерує читабельну картку зі стилізованою панорамою Києва."""
    image = _gradient_background()
    draw = ImageDraw.Draw(image, "RGBA")

    font_kicker = _font(17, bold=True)
    font_title = _font(37, bold=True)
    font_subtitle = _font(19)
    font_district = _font(20, bold=True)
    font_price = _font(19, bold=True)
    font_footer = _font(14)

    # Верхня шапка.
    draw.rounded_rectangle((42, 32, 320, 65), radius=16,
                           fill=(28, 166, 190, 45),
                           outline=(84, 220, 224, 150), width=1)
    draw.text((58, 39), "КИЇВ  •  РИНОК ЖИТЛА", font=font_kicker, fill="#78E3E0")
    draw.text((42, 79), "Скільки коштує квадратний метр?", font=font_title, fill="#FFFFFF",
              stroke_width=0)
    draw.text((45, 129), f"Середня вартість житла за районами  |  {month_str}",
              font=font_subtitle, fill="#B9D7E8")
    draw.line((42, 165, 1158, 165), fill=(105, 206, 220, 150), width=2)

    items = sorted(
        data_dict.items(),
        key=lambda item: _price_number(item[1].get("avg", "")),
        reverse=True,
    )
    if not items:
        items = [("Дані відсутні", {"avg": "—"})]

    # Дві колонки. До 10 районів — повний список; інші рівномірно діляться.
    midpoint = (len(items) + 1) // 2
    columns = [items[:midpoint], items[midpoint:]]
    col_x = [42, 612]
    col_w = 546
    row_h = 70
    y_start = 183

    for col_index, column in enumerate(columns):
        x = col_x[col_index]
        for row_index, (district, details) in enumerate(column):
            y = y_start + row_index * row_h
            if y + row_h - 7 > 598:
                break
            # Напівпрозорі рядки — як інформаційні картки, а не таблиця з Excel.
            draw.rounded_rectangle(
                (x, y, x + col_w, y + row_h - 8),
                radius=13,
                fill=(9, 27, 47, 205),
                outline=(111, 177, 202, 85),
                width=1,
            )
            draw.rounded_rectangle((x + 12, y + 17, x + 17, y + 48),
                                   radius=2, fill=(63, 214, 205, 255))
            district = re.sub(r"\s+район$", "", str(district).strip(), flags=re.IGNORECASE)
            district = _fit_text(draw, district, font_district, 310)
            draw.text((x + 30, y + 12), district, font=font_district, fill="#F3F8FC")
            price = str(details.get("avg", "—")).strip()
            price_label = f"{price} $/м²"
            price_width = draw.textbbox((0, 0), price_label, font=font_price)[2]
            draw.text((x + col_w - price_width - 17, y + 17), price_label,
                      font=font_price, fill="#76F0C1")

    # Нижній підпис.
    draw.line((42, 606, 1158, 606), fill=(105, 206, 220, 110), width=1)
    draw.text((44, 620), "Джерело: АН «Благовіст»", font=font_footer, fill="#B6C9D7")
    footer_right = "КИЇВСЬКИЙ НЕ ГІДРОМЕТЦЕНТР"
    right_width = draw.textbbox((0, 0), footer_right, font=font_footer)[2]
    draw.text((1156 - right_width, 620), footer_right, font=font_footer, fill="#78E3E0")

    image.save(output_path, format="JPEG", quality=94, optimize=True)
    return output_path


if __name__ == "__main__":
    sample_data = {
        "Голосіївський район": {"avg": "1850"},
        "Дарницький район": {"avg": "1320"},
        "Деснянський район": {"avg": "980"},
        "Дніпровський район": {"avg": "1410"},
        "Оболонський район": {"avg": "1450"},
        "Печерський район": {"avg": "3100"},
        "Подільський район": {"avg": "1600"},
        "Святошинський район": {"avg": "1200"},
        "Солом'янський район": {"avg": "1400"},
        "Шевченківський район": {"avg": "2450"},
    }
    generate_real_estate_card(sample_data, "Жовтень 2026")
