import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from statystyka_nerukhomosti_card import generate_real_estate_card

SOURCE_URL = "https://blagovist.ua/uk/realtystat/{period}"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def get_current_period():
    """Поточний звітний місяць у форматі YYYY-MM."""
    return datetime.now().strftime("%Y-%m")


def parse_price(value):
    """Повертає очищене значення ціни, не змінюючи її точність."""
    value = re.sub(r"\s+", "", str(value)).replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", value)
    return match.group(0) if match else None


def fetch_realty_data(period):
    """Завантажує статистику з сайту АН «Благовіст»."""
    url = SOURCE_URL.format(period=period)
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        data = {}

        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cols = row.find_all(["td", "th"])
                if len(cols) < 3:
                    continue

                district_name = cols[0].get_text(" ", strip=True)
                raw_price = cols[2].get_text(" ", strip=True)
                price = parse_price(raw_price)

                # Назва району на сайті може бути як із словом «район»,
                # так і без нього. Відсікаємо заголовки та порожні рядки.
                normalized = district_name.lower()
                looks_like_district = (
                    district_name
                    and (
                        "район" in normalized
                        or normalized.endswith("ський")
                        or normalized.endswith("цький")
                        or normalized.endswith("зький")
                    )
                )
                if looks_like_district and price:
                    data[district_name] = {"avg": price}

        return data or None
    except requests.RequestException as exc:
        print(f"Не вдалося завантажити статистику з джерела: {exc}")
    except Exception as exc:
        print(f"Помилка під час обробки статистики: {exc}")
    return None


def build_telegram_text(data, period, using_fallback=False):
    """Формує читабельний допис із коротким поясненням та висновком."""
    month_names = {
        "01": "січень", "02": "лютий", "03": "березень",
        "04": "квітень", "05": "травень", "06": "червень",
        "07": "липень", "08": "серпень", "09": "вересень",
        "10": "жовтень", "11": "листопад", "12": "грудень",
    }
    year, month = period.split("-")
    period_label = f"{month_names.get(month, month)} {year}"

    lines = [
        "🏙️ *Київська нерухомість: ціна квадратного метра*",
        f"📅 Період спостереження: *{period_label}*",
        "",
        "Київський ринок житла — це мозаїка з десяти районів, "
        "різних локацій і різних можливостей. Середня ціна за м² "
        "допомагає побачити загальну картину, але за кожною цифрою "
        "стоять стан будинку, транспорт, інфраструктура та тип житла.",
        "",
        "📊 *Середня вартість за районами*",
    ]

    def price_key(item):
        try:
            return float(str(item[1].get("avg", "0")).replace(",", "."))
        except (TypeError, ValueError):
            return -1

    for district, info in sorted(data.items(), key=price_key, reverse=True):
        name = district.strip()
        name = re.sub(r"\s+район$", "", name, flags=re.IGNORECASE)
        price = str(info.get("avg", "—")).strip()
        lines.append(f"▪️ *{name}* — `{price} $/м²`")

    lines.extend([
        "",
        "💡 *Як читати ці цифри?*",
        "Середня ціна — це орієнтир для порівняння, а не гарантована "
        "вартість конкретної квартири. На ціну впливають тип будинку, "
        "стан помешкання, розташування та умови продажу.",
        "",
        "_Ринок нерухомості — це не лише ціна квадратного метра, "
        "а й вибір того, як і де хочеться жити._",
        "",
        "📌 Джерело даних: АН «Благовіст».",
        "📣 Більше корисних спостережень — у каналі «Київський не гідрометцентр».",
        "",
        "#Київ #НерухомістьКиєва #ЦіниНаЖитло",
    ])

    if using_fallback:
        lines.insert(
            3,
            "⚠️ _Джерело тимчасово недоступне. Нижче наведено резервні "
            "значення для демонстрації, а не підтверджену актуальну статистику._",
        )

    return "\n".join(lines)


def send_to_telegram(image_path, text_message, token, chat_id):
    """Надсилає картку й текст окремими повідомленнями та перевіряє відповіді API."""
    photo_url = TELEGRAM_API.format(token=token, method="sendPhoto")
    with open(image_path, "rb") as photo_file:
        photo_response = requests.post(
            photo_url,
            data={"chat_id": chat_id},
            files={"photo": photo_file},
            timeout=30,
        )
    photo_response.raise_for_status()
    photo_result = photo_response.json()
    if not photo_result.get("ok"):
        raise RuntimeError(f"Telegram не прийняв картку: {photo_result}")

    message_url = TELEGRAM_API.format(token=token, method="sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text_message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    message_response = requests.post(message_url, json=payload, timeout=30)
    message_response.raise_for_status()
    message_result = message_response.json()
    if not message_result.get("ok"):
        raise RuntimeError(f"Telegram не прийняв текст: {message_result}")


if __name__ == "__main__":
    period = get_current_period()
    print(f"Збираємо статистику за період: {period}")

    raw_data = fetch_realty_data(period)
    using_fallback = False

    if not raw_data:
        # Залишаємо резервний набір для сумісності з наявним проєктом,
        # але позначаємо його в публікації як демонстраційний.
        print("Увага: джерело не повернуло дані. Буде використано резервний набір.")
        using_fallback = True
        raw_data = {
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

    month_names = {
        "01": "Січень", "02": "Лютий", "03": "Березень",
        "04": "Квітень", "05": "Травень", "06": "Червень",
        "07": "Липень", "08": "Серпень", "09": "Вересень",
        "10": "Жовтень", "11": "Листопад", "12": "Грудень",
    }
    year, month = period.split("-")
    card_period = f"{month_names.get(month, month)} {year}"
    card_path = generate_real_estate_card(raw_data, card_period)
    text_msg = build_telegram_text(raw_data, period, using_fallback)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if bot_token and chat_id:
        send_to_telegram(card_path, text_msg, bot_token, chat_id)
        print("Картку та текст успішно надіслано до Telegram.")
    else:
        print("Попередження: TELEGRAM_BOT_TOKEN або CHAT_ID не знайдені в GitHub Secrets.")
