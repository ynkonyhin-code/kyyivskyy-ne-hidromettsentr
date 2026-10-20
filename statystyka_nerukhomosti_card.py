from PIL import Image, ImageDraw, ImageFont
import os

def generate_real_estate_card(data_dict, month_str, output_path="realty_card.jpg"):
    width, height = 1200, 675
    image = Image.new("RGB", (width, height), color="#0F172A") # Стильный темно-синий
    draw = ImageDraw.Draw(image)

    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
        font_subtitle = ImageFont.truetype("arial.ttf", 22)
        font_text = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font_title = ImageFont.load_default()
        font_subtitle = ImageFont.load_default()
        font_text = ImageFont.load_default()

    # Шапка
    draw.text((50, 40), "КИЇВСЬКИЙ НЕДВИЖИМОСТНИЙ ДАЙДЖЕСТ", fill="#38BDF8", font=font_title)
    draw.text((50, 90), f"Середня вартість житла за районами ({month_str})", fill="#94A3B8", font=font_subtitle)
    draw.line([(50, 130), (1150, 130)], fill="#334155", width=2)

    # Вывод в две колонки по 5 районов
    items = list(data_dict.items())
    col1 = items[:5]
    col2 = items[5:10]

    y_start = 160
    # Колонка 1
    for i, (district, prices) in enumerate(col1):
        y = y_start + (i * 85)
        draw.text((50, y), f"📍 {district}", fill="#F8FAFC", font=font_text)
        avg_val = prices.get('avg', 'N/A')
        draw.text((50, y + 30), f"Середня ціна: {avg_val} $/м²", fill="#34D399", font=font_text)

    # Колонка 2
    for i, (district, prices) in enumerate(col2):
        y = y_start + (i * 85)
        draw.text((600, y), f"📍 {district}", fill="#F8FAFC", font=font_text)
        avg_val = prices.get('avg', 'N/A')
        draw.text((600, y + 30), f"Середня ціна: {avg_val} $/м²", fill="#34D399", font=font_text)

    # Подвал
    draw.line([(50, 600), (1150, 600)], fill="#334155", width=1)
    draw.text((50, 615), "Джерело: АН «Благовіст»  |  Канал: Київський не гідрометцентр", fill="#64748B", font=font_subtitle)

    image.save(output_path, quality=95)
    return output_path

if __name__ == "__main__":
    sample_data = {
        "Голосіївський": {"avg": "1850"},
        "Дарницький": {"avg": "1320"},
        "Деснянський": {"avg": "980"},
        "Дніпровський": {"avg": "1410"},
        "Оболонський": {"avg": "1450"},
        "Печерський": {"avg": "3100"},
        "Подільський": {"avg": "1600"},
        "Святошинський": {"avg": "1200"},
        "Солом'янський": {"avg": "1400"},
        "Шевченківський": {"avg": "2450"},
    }
    generate_real_estate_card(sample_data, "Жовтень 2026")
