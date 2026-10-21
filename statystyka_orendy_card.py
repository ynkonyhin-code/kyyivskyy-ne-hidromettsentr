# -*- coding: utf-8 -*-
"""
Картки «Оренда квартир у Києві» (канал «Київський не гідрометцентр»), 1200×675.
  render_main_card — рейтинг районів за орендою однокімнатної + 2-/3-кімнатні + рух за місяць;
  render_heat_card — «теплова карта» оренди за кімнатністю (1–4) і середня за квартиру.
Дані — словник з analyze() у statystyka_orendy.py. Шрифт — DejaVu Sans (на runner-і: fonts-dejavu-core).
Модуль самодостатній (стиль збігається з карткою «Київська нерухомість»).
"""
from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 675
BG_TOP, BG_BOT = (5, 14, 31), (11, 33, 58)
ACC, TXT, MUT = (94, 234, 212), (240, 247, 255), (146, 172, 196)
UP, DOWN, SAME = (255, 175, 105), (120, 200, 255), (146, 172, 196)
PANEL, LINE = (18, 40, 68, 190), (58, 96, 128)
FONTS = {True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
         False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]}
BRAND = "КИЇВСЬКИЙ НЕ ГІДРОМЕТЦЕНТР"
ARROW = {"up": ("▲", UP), "down": ("▼", DOWN), "same": ("■", SAME), None: ("", MUT)}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in FONTS[bold]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _k(v: Optional[int]) -> str:
    return "—" if v is None else f"{v / 1000:.1f}".replace(".", ",")


def _right(d, x, y, text, font, fill):
    d.text((x - d.textlength(text, font=font), y), text, font=font, fill=fill)


def _wrap(d, text: str, font, maxw: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split(", "):
        t = (cur + ", " + w) if cur else w
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur + ",")
            cur = w
    return lines + ([cur] if cur else [])


def _background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((520, -260, 1180, 260), fill=(40, 110, 150, 55))
    return Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(70)))


def _panel(img: Image.Image, box, radius: int = 14, fill=PANEL) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill, outline=LINE + (255,), width=1)
    img.alpha_composite(layer)


def _header(img: Image.Image, title: str, subtitle: str) -> None:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((42, 28, 336, 62), radius=17, outline=ACC + (255,), width=1, fill=(20, 60, 80, 120))
    d.text((60, 36), "КИЇВ  •  ОРЕНДА ЖИТЛА", font=_font(16, True), fill=ACC)
    d.text((42, 76), title, font=_font(44, True), fill=TXT)
    d.text((44, 138), subtitle, font=_font(20), fill=MUT)
    d.line([(42, 176), (W - 42, 176)], fill=LINE, width=2)


def _footer(img: Image.Image, note: str) -> None:
    d = ImageDraw.Draw(img)
    d.line([(42, 626), (W - 42, 626)], fill=LINE, width=1)
    d.text((44, 640), note, font=_font(15), fill=MUT)
    _right(d, W - 42, 640, BRAND, _font(15, True), ACC)


# ── Картка 1 ───────────────────────────────────────────────────────────────────
def render_main_card(a: dict, asof: str, out: str) -> str:
    img = _background()
    _header(img, "Скільки коштує оренда квартири?", f"Місячна оренда за районами, тис. грн  |  станом на {asof}")
    rows = a["rows"]
    vmax = max(r["r1"] for r in rows)
    x_name, x_bar, bar_w, x1, x2, x3, x_dir = 52, 270, 150, 505, 595, 685, 752
    top, rh = 204, 40
    d = ImageDraw.Draw(img)
    for x, lab in ((x1, "1-кімн."), (x2, "2-кімн."), (x3, "3-кімн.")):
        _right(d, x, 184, lab, _font(13), MUT)
    _right(d, x_dir + 8, 184, "місяць", _font(13), MUT)
    for i, r in enumerate(rows):
        y = top + i * rh
        _panel(img, (42, y, 772, y + rh - 5), radius=10, fill=(16, 36, 62, 140))
        d = ImageDraw.Draw(img)
        d.text((x_name, y + 7), r["name"], font=_font(19, True), fill=TXT)
        bl = max(6, int(bar_w * r["r1"] / vmax))
        d.rounded_rectangle((x_bar, y + 12, x_bar + bar_w, y + 22), radius=5, fill=(24, 54, 84))
        d.rounded_rectangle((x_bar, y + 12, x_bar + bl, y + 22), radius=5, fill=ACC)
        _right(d, x1, y + 7, _k(r["r1"]), _font(20, True), ACC)
        _right(d, x2, y + 8, _k(r["r2"]), _font(18), TXT)
        _right(d, x3, y + 8, _k(r["r3"]), _font(18), TXT)
        sym, col = ARROW.get(r["dir"], ARROW[None])
        _right(d, x_dir + 8, y + 9, sym, _font(17, True), col)

    _panel(img, (798, 190, W - 42, 610), radius=16)
    d = ImageDraw.Draw(img)
    px = 822
    d.text((px, 206), "РІЗНИЦЯ МІЖ РАЙОНАМИ", font=_font(14, True), fill=MUT)
    d.text((px, 228), f"{a['ratio']:.1f}".replace(".", ",") + "×", font=_font(52, True), fill=ACC)
    d.text((px, 292), f"{a['hi']['name']} проти {a['lo']['name']}", font=_font(13), fill=MUT)
    d.text((px, 310), "(однокімнатна)", font=_font(13), fill=MUT)
    d.line([(px, 340), (W - 66, 340)], fill=LINE, width=1)
    d.text((px, 354), "ЩО ЗА МІСЯЦЬ (оцінка DIM.RIA)", font=_font(14, True), fill=MUT)
    y = 380
    for key, title in (("up", "Дорожчає"), ("down", "Дешевшає"), ("same", "Без змін")):
        names = a["dirs"][key]
        if not names:
            continue
        sym, col = ARROW[key]
        d.text((px, y), f"{sym} {title}", font=_font(15, True), fill=col)
        y += 22
        for line in _wrap(d, ", ".join(names), _font(13), W - 66 - px)[:3]:
            d.text((px + 2, y), line, font=_font(13), fill=TXT)
            y += 18
        y += 6
    m = a.get("meta") or {}
    ny = 566
    if m.get("listings"):
        d.text((px, ny), "У ВИБІРЦІ", font=_font(13, True), fill=MUT)
        d.text((px, ny + 17), f"{m['listings']:,} оголошень".replace(",", " "), font=_font(16, True), fill=TXT)
    if m.get("rate"):
        d.text((px + 150, ny), "КУРС DIM.RIA", font=_font(13, True), fill=MUT)
        d.text((px + 150, ny + 17), f"1 $ = {str(m['rate']).replace('.', ',')} грн", font=_font(16, True), fill=TXT)
    _footer(img, "Джерело: DIM.RIA (dom.ria.com) · ціни з оголошень, не підписаних договорів")
    img.convert("RGB").save(out)
    return out


# ── Картка 2: теплова карта ────────────────────────────────────────────────────
def _heat(v: Optional[int], lo: int, hi: int) -> tuple:
    if v is None:
        return (16, 36, 62, 90)
    t = 0 if hi == lo else (v - lo) / (hi - lo)
    return (int(26 + 40 * t), int(70 + 150 * t), int(100 + 90 * t), 235)


def render_heat_card(a: dict, asof: str, out: str) -> str:
    img = _background()
    _header(img, "Оренда: від 1 до 4 кімнат", f"Місячна оренда за кімнатністю, тис. грн  |  станом на {asof}")
    rows = a["rows"]
    cols = [("r1", "1-кімн."), ("r2", "2-кімн."), ("r3", "3-кімн."), ("r4", "4-кімн."), ("avg", "середня за квартиру")]
    x0, name_w, cw, top, rh = 42, 250, 172, 214, 38
    d = ImageDraw.Draw(img)
    for j, (_, lab) in enumerate(cols):
        cx = x0 + name_w + j * cw
        if j == 4:
            lab1, lab2 = "середня", "за квартиру"
            d.text((cx + 12, 184), lab1, font=_font(13), fill=MUT)
            d.text((cx + 12, 199), lab2, font=_font(13), fill=MUT)
        else:
            d.text((cx + 12, 190), lab, font=_font(14, True), fill=MUT)
    rng = {k: (min(v for v in (r[k] for r in rows) if v is not None), max(v for v in (r[k] for r in rows) if v is not None))
           for k, _ in cols}
    for i, r in enumerate(rows):
        y = top + i * rh
        d.text((x0 + 8, y + 8), r["name"], font=_font(19, True), fill=TXT)
        for j, (k, _) in enumerate(cols):
            cx = x0 + name_w + j * cw
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rounded_rectangle((cx + 4, y + 2, cx + cw - 6, y + rh - 4), radius=8,
                                                    fill=_heat(r[k], *rng[k]))
            img.alpha_composite(layer)
            d = ImageDraw.Draw(img)
            v = r[k]
            txt = _k(v)
            d.text((cx + cw / 2 - d.textlength(txt, font=_font(19, True)) / 2 - 1, y + 7), txt,
                   font=_font(19, True), fill=(250, 253, 255) if v is not None else MUT)
    _footer(img, "Колір — відносно інших районів у колонці · «—» = замало оголошень · 4-кімн.: вибірка мала, цифри нестабільні")
    img.convert("RGB").save(out)
    return out
