"""Thẻ thiếu nhi (PDF in A4, 9 thẻ/trang, kích thước thẻ CR80 dọc 54 x 85.6 mm)
và gói ảnh QR (ZIP).

Ảnh QR trên thẻ chính là ảnh đã qua bước tự kiểm tra giải mã trong qrimage.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from fpdf import FPDF
from PIL import Image

from . import config, qrimage
from .textutil import strip_accents

CARD_W, CARD_H = 54.0, 85.6
COLS, ROWS, GAP = 3, 3, 4.0


@dataclass
class CardData:
    code: str
    saint_name: str
    full_name: str
    class_name: str
    branch: str
    payload: str


@dataclass
class CardStyle:
    xudoan_name: str
    parish_name: str
    year_name: str
    primary: str = "#1B2A4A"
    accent: str = "#D4A017"
    fg: str = "#000000"
    logo: Image.Image | None = None  # logo trên dải đầu thẻ
    qr_logo: Image.Image | None = None  # logo giữa QR (None = QR không logo)
    qr_logo_ratio: float = qrimage.DEFAULT_LOGO_RATIO


@dataclass
class CardReport:
    pdf: bytes
    total: int
    without_logo: list[str]
    unverified: list[str]


def _rgb(color: str) -> tuple[int, int, int]:
    return qrimage.hex_to_rgb(color)


def _png(img: Image.Image, palette: bool = True) -> io.BytesIO:
    buf = io.BytesIO()
    if palette:
        img = img.convert("RGB").quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


class _CardPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)
        fonts = config.FONTS_DIR
        self.add_font("BVP", "", str(fonts / "BeVietnamPro-Regular.ttf"))
        self.add_font("BVP", "B", str(fonts / "BeVietnamPro-Bold.ttf"))
        self.add_font("BVP", "I", str(fonts / "BeVietnamPro-SemiBold.ttf"))
        self.set_title("The thieu nhi")
        self.set_creator("He thong diem danh TNTT")


def _fit_size(pdf: FPDF, text: str, style: str, max_w: float, start: float, minimum: float) -> float:
    size = start
    while size > minimum:
        pdf.set_font("BVP", style, size)
        if pdf.get_string_width(text) <= max_w:
            break
        size -= 0.25
    return size


def _draw_card(pdf: FPDF, x: float, y: float, card: CardData, style: CardStyle, qr_png: io.BytesIO,
               logo_png: io.BytesIO | None) -> None:
    primary, accent = _rgb(style.primary), _rgb(style.accent)
    # viền cắt
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.2)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(x, y, CARD_W, CARD_H, style="DF", round_corners=True, corner_radius=3)
    # dải đầu thẻ
    pdf.set_fill_color(*primary)
    pdf.rect(x, y, CARD_W, 21, style="F", round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=3)
    pdf.set_fill_color(*accent)
    pdf.rect(x, y + 21, CARD_W, 0.9, style="F")
    text_x = x + 3
    if logo_png is not None:
        pdf.set_fill_color(255, 255, 255)
        pdf.ellipse(x + 2.2, y + 2.7, 15.6, 15.6, style="F")
        pdf.image(logo_png, x + 3, y + 3.5, 14, 14)
        text_x = x + 19.5
    text_w = x + CARD_W - 2 - text_x
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("BVP", "B", 7)
    pdf.set_xy(text_x, y + 3.2)
    pdf.multi_cell(text_w, 3.3, style.xudoan_name.upper(), align="L", max_line_height=3.3)
    pdf.set_text_color(*accent)
    pdf.set_font("BVP", "", 5.6)
    pdf.set_x(text_x)
    pdf.multi_cell(text_w, 2.8, style.parish_name, align="L")
    # QR giữa thẻ
    qr_size = 41
    pdf.image(qr_png, x + (CARD_W - qr_size) / 2, y + 24, qr_size, qr_size)
    # thông tin
    pdf.set_text_color(*primary)
    cy = y + 66.2
    if card.saint_name:
        pdf.set_font("BVP", "I", _fit_size(pdf, card.saint_name, "I", CARD_W - 6, 7.5, 5.5))
        pdf.set_text_color(*_darken(accent))
        pdf.set_xy(x + 2, cy)
        pdf.cell(CARD_W - 4, 3.4, card.saint_name, align="C")
        cy += 3.6
    pdf.set_text_color(*primary)
    pdf.set_font("BVP", "B", _fit_size(pdf, card.full_name, "B", CARD_W - 5, 10.5, 6.5))
    pdf.set_xy(x + 2, cy)
    pdf.cell(CARD_W - 4, 4.6, card.full_name, align="C")
    cy += 5.0
    pdf.set_font("BVP", "", 6.6)
    pdf.set_text_color(70, 78, 96)
    line = " · ".join(p for p in (card.class_name and f"Lớp {card.class_name}", card.branch) if p)
    pdf.set_xy(x + 2, cy)
    pdf.cell(CARD_W - 4, 3, line or " ", align="C")
    cy += 3.3
    pdf.set_font("BVP", "B", 6.6)
    pdf.set_xy(x + 2, cy)
    pdf.cell(CARD_W - 4, 3, f"Mã: {card.code}   ·   {style.year_name}", align="C")
    # dải chân
    pdf.set_fill_color(*accent)
    pdf.rect(x, y + CARD_H - 2.2, CARD_W, 2.2, style="F", round_corners=("BOTTOM_LEFT", "BOTTOM_RIGHT"),
             corner_radius=2.2)


def _darken(rgb, factor: float = 0.75):
    return tuple(int(c * factor) for c in rgb)


def _crop_marks(pdf: FPDF, x0: float, y0: float) -> None:
    pdf.set_draw_color(170, 170, 170)
    pdf.set_line_width(0.15)
    xs = [x0 + c * (CARD_W + GAP) for c in range(COLS)]
    ys = [y0 + r * (CARD_H + GAP) for r in range(ROWS)]
    for x in xs + [x + CARD_W for x in xs]:
        pdf.line(x, y0 - 6, x, y0 - 2)
    for y in ys + [y + CARD_H for y in ys]:
        pdf.line(x0 - 6, y, x0 - 2, y)


def build_cards_pdf(cards: list[CardData], style: CardStyle, progress=None) -> CardReport:
    pdf = _CardPDF()
    page_w, page_h = 210, 297
    x0 = (page_w - (COLS * CARD_W + (COLS - 1) * GAP)) / 2
    y0 = (page_h - (ROWS * CARD_H + (ROWS - 1) * GAP)) / 2
    logo_png = _png(style.logo, palette=False) if style.logo is not None else None
    without_logo, unverified = [], []
    per_page = COLS * ROWS
    for i, card in enumerate(cards):
        if i % per_page == 0:
            pdf.add_page()
            _crop_marks(pdf, x0, y0)
        res = qrimage.make_qr(card.payload, logo=style.qr_logo, logo_ratio=style.qr_logo_ratio,
                              fg=style.fg, module_px=16)
        if style.qr_logo is not None and not res.logo_applied:
            without_logo.append(card.code)
        if not res.verified:
            unverified.append(card.code)
        slot = i % per_page
        cx = x0 + (slot % COLS) * (CARD_W + GAP)
        cy = y0 + (slot // COLS) * (CARD_H + GAP)
        if logo_png is not None:
            logo_png.seek(0)
        _draw_card(pdf, cx, cy, card, style, _png(res.image), logo_png)
        if progress:
            progress((i + 1) / len(cards))
    return CardReport(bytes(pdf.output()), len(cards), without_logo, unverified)


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", strip_accents(text)).strip("_")[:60] or "qr"


def build_qr_zip(cards: list[CardData], *, logo: Image.Image | None, logo_ratio: float, fg: str,
                 with_label: bool = False, progress=None) -> tuple[bytes, list[str]]:
    """ZIP các file PNG QR (tên file = mã + tên không dấu)."""
    buf = io.BytesIO()
    problems = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, card in enumerate(cards):
            res = qrimage.make_qr(card.payload, logo=logo, logo_ratio=logo_ratio, fg=fg, module_px=16)
            if not res.verified:
                problems.append(card.code)
            img = labeled(res.image, card) if with_label else res.image
            zf.writestr(f"{safe_filename(card.code)}_{safe_filename(card.full_name)}.png", qrimage.to_png(img))
            if progress:
                progress((i + 1) / len(cards))
    return buf.getvalue(), problems


def labeled(qr_img: Image.Image, card: CardData) -> Image.Image:
    from PIL import ImageDraw

    from .services.branding import font

    w = qr_img.width
    out = Image.new("RGB", (w, w + 110), "white")
    out.paste(qr_img, (0, 0))
    d = ImageDraw.Draw(out)
    name = f"{card.saint_name} {card.full_name}".strip()
    size = 34
    while size > 16 and d.textlength(name, font=font("Bold", size)) > w - 20:
        size -= 2
    d.text((w / 2, w + 8), name, font=font("Bold", size), fill="#1B2A4A", anchor="ma")
    d.text((w / 2, w + 60), f"{card.code} · {card.class_name}", font=font("Regular", 26), fill="#4A5468", anchor="ma")
    return out
