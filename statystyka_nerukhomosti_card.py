# -*- coding: utf-8 -*-
"""
Картки «Київська нерухомість» (канал «Київський не гідрометцентр»), 1200×675.
  render_price_card — «Скільки коштує квадратний метр?»: 10 районів, зміна до місяця/року, цифри по Києву;
  render_micro_card — «Мікрорайони: де дорожче, де дешевше».
Дані — словник з analyze() у statystyka_nerukhomosti.py. Шрифт — DejaVu Sans (є на runner-і: fonts-dejavu-core).
"""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 675
BG_TOP, BG_BOT = (5, 14, 31), (11, 33, 58)
ACC, TXT, MUT = (94, 234, 212), (240, 247, 255), (146, 172, 196)
GREEN, RED = (110, 226, 160), (255, 128, 128)
PANEL, LINE = (18, 40, 68, 190), (58, 96, 128)
FONTS = {True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
         False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]}
BRAND = "КИЇВСЬКИЙ НЕ ГІДРОМЕТЦЕНТР"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in FONTS[bold]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _money(v: float) -> str:
    return f"${round(v):,}".replace(",", " ")


def _n(v: float) -> str:
    t = f"{v:,.1f}".replace(",", " ").replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def _pct(v: Optional[float]) -> tuple[str, tuple]:
    if v is None:
        return "—", MUT
    arrow = "▲" if v > 0.05 else "▼" if v < -0.05 else "■"
    col = GREEN if v > 0.05 else RED if v < -0.05 else MUT
    return f"{arrow} {abs(v):.1f}%".replace(".", ","), col


def _fit(d: ImageDraw.ImageDraw, text: str, font, maxw: int) -> str:
    if d.textlength(text, font=font) <= maxw:
        return text
    while text and d.textlength(text + "…", font=font) > maxw:
        text = text[:-1]
    return text.rstrip() + "…"


def _right(d, x, y, text, font, fill):
    d.text((x - d.textlength(text, font=font), y), text, font=font, fill=fill)


def _background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((520, -260, 1180, 260), fill=(40, 110, 150, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(img.convert("RGBA"), glow)


def _panel(img: Image.Image, box, radius: int = 14, fill=PANEL) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill, outline=LINE + (255,), width=1)
    img.alpha_composite(layer)


def _header(img: Image.Image, title: str, subtitle: str) -> None:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((42, 28, 336, 62), radius=17, outline=ACC + (255,), width=1, fill=(20, 60, 80, 120))
    d.text((60, 36), "КИЇВ  •  РИНОК ЖИТЛА", font=_font(16, True), fill=ACC)
    d.text((42, 76), title, font=_font(44, True), fill=TXT)
    d.text((44, 138), subtitle, font=_font(20), fill=MUT)
    d.line([(42, 176), (W - 42, 176)], fill=LINE, width=2)


def _footer(img: Image.Image, note: str) -> None:
    d = ImageDraw.Draw(img)
    d.line([(42, 626), (W - 42, 626)], fill=LINE, width=1)
    d.text((44, 640), note, font=_font(15), fill=MUT)
    _right(d, W - 42, 640, BRAND, _font(15, True), ACC)


# ── Картка 1: райони ───────────────────────────────────────────────────────
def render_price_card(a: dict, period_label: str, out: str) -> str:
    img = _background()
    _header(img, "Скільки коштує квадратний метр?", f"Середня ціна за м² у районах Києва  |  {period_label}")
    ds, city = a["districts"], a["city"]
    vmax = max(d["sqm"] for d in ds)
    x_name, x_bar, bar_w, x_val, x_mom = 52, 284, 250, 650, 758
    top, rh = 204, 40

    d = ImageDraw.Draw(img)
    _right(d, x_val, 184, "$ / м²", _font(13), MUT)
    _right(d, x_mom, 184, "до поп. міс.", _font(13), MUT)
    for i, row in enumerate(ds):
        y = top + i * rh
        _panel(img, (42, y, 772, y + rh - 5), radius=10, fill=(16, 36, 62, 140))
        d = ImageDraw.Draw(img)
        d.text((x_name, y + 7), row["name"], font=_font(20, True), fill=TXT)
        bl = max(6, int(bar_w * row["sqm"] / vmax))
        d.rounded_rectangle((x_bar, y + 11, x_bar + bar_w, y + 22), radius=5, fill=(24, 54, 84))
        d.rounded_rectangle((x_bar, y + 11, x_bar + bl, y + 22), radius=5, fill=ACC)
        _right(d, x_val, y + 6, _money(row["sqm"]), _font(21, True), ACC)
        txt, col = _pct(row["mom"])
        _right(d, x_mom, y + 9, txt, _font(16, True), col)

    # права панель: Київ загалом
    _panel(img, (798, 190, W - 42, 610), radius=16)
    d = ImageDraw.Draw(img)
    px = 822
    d.text((px, 208), "КИЇВ ЗАГАЛОМ", font=_font(15, True), fill=MUT)
    d.text((px, 230), _money(city["sqm"]), font=_font(54, True), fill=ACC)
    d.text((px + d.textlength(_money(city["sqm"]), font=_font(54, True)) + 10, 262), "за м²", font=_font(20), fill=MUT)
    for j, (lab, v) in enumerate((("до попереднього місяця", city["mom"]), ("за рік", city["yoy"]))):
        t, col = _pct(v)
        d.text((px, 306 + j * 28), t, font=_font(18, True), fill=col)
        d.text((px + 100, 308 + j * 28), lab, font=_font(15), fill=MUT)
    d.line([(px, 372), (W - 66, 372)], fill=LINE, width=1)
    d.text((px, 386), "КВАРТИРИ ПО КИЄВУ, ТИС. $", font=_font(15, True), fill=MUT)
    _right(d, 1036, 412, "типово", _font(13), MUT)
    _right(d, W - 66, 412, "від – до", _font(13), MUT)
    for j, k in enumerate((1, 2, 3)):
        r = city["rooms"].get(k)
        if not r:
            continue
        y = 436 + j * 40
        d.text((px, y + 2), f"{k}-кімн.", font=_font(19, True), fill=TXT)
        _right(d, 1036, y, _n(r["avg"]), _font(22, True), ACC)
        _right(d, W - 66, y + 4, f"{_n(r['min'])}–{_n(r['max'])}", _font(15), MUT)
    d.text((px, 566), "«Від – до» — крайні значення,", font=_font(13), fill=MUT)
    d.text((px, 584), "часто поодинокі об'єкти.", font=_font(13), fill=MUT)

    _footer(img, "Джерело: АН «Благовіст» (blagovist.ua) · база агенції, не офіційна статистика угод")
    img.convert("RGB").save(out)
    return out


# ── Картка 2: мікрорайони ──────────────────────────────────────────────────
def render_micro_card(a: dict, period_label: str, out: str) -> str:
    img = _background()
    _header(img, "Мікрорайони: де дорожче, де дешевше", f"Ціна за м² у мікрорайонах Києва  |  {period_label}")
    blocks = ((42, "НАЙДОРОЖЧІ", a["top"], ACC), (618, "НАЙДЕШЕВШІ", a["bottom"], (140, 190, 255)))
    for x0, title, items, col in blocks:
        _panel(img, (x0, 190, x0 + 540, 610), radius=16)
        d = ImageDraw.Draw(img)
        d.text((x0 + 24, 206), title, font=_font(16, True), fill=col)
        _right(d, x0 + 516, 208, "$ / м²", _font(13), MUT)
        for i, m in enumerate(items[:6]):
            y = 240 + i * 60
            d.text((x0 + 24, y + 6), str(i + 1), font=_font(26, True), fill=col)
            d.text((x0 + 66, y), _fit(d, m["name"], _font(21, True), 320), font=_font(21, True), fill=TXT)
            if m.get("parent"):
                d.text((x0 + 66, y + 28), f"{m['parent']} район", font=_font(14), fill=MUT)
            _right(d, x0 + 516, y + 8, _money(m["sqm"] * 1000), _font(24, True), col)
            if i < 5:
                d.line([(x0 + 24, y + 54), (x0 + 516, y + 54)], fill=(40, 70, 100), width=1)
    _footer(img, "Мікрорайони з даними щонайменше за двома типами квартир · частина вибірок невелика")
    img.convert("RGB").save(out)
    return out
