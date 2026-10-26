"""Sinh ảnh QR (có/không logo, trắng đen/màu nhận diện) và tự kiểm tra giải mã.

Nguyên tắc an toàn khi chèn logo:
- Mức sửa lỗi H (~30% codeword phục hồi được).
- Version tối thiểu 3 khi có logo: ma trận đủ lớn, vùng trung tâm KHÔNG có
  alignment pattern (version >= 7 mới có), logo không chạm finder/timing pattern.
- Logo nằm trên nền trắng bo góc, chiều rộng vùng che <= 30% cạnh QR
  (diện tích <= 9%), căn theo lưới module.
- Sau khi dựng ảnh: giải mã lại bằng OpenCV (và pyzbar nếu có) trên ảnh gốc
  + ảnh thu nhỏ/làm mờ (mô phỏng in/chụp). Không đạt -> giảm logo; vẫn không
  đạt -> bỏ logo.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFilter
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M

MAX_LOGO_RATIO = 0.30
MIN_LOGO_RATIO = 0.12
DEFAULT_LOGO_RATIO = 0.24
_STEP = 0.03


@dataclass
class QrResult:
    image: Image.Image
    payload: str
    logo_requested: bool
    logo_applied: bool
    logo_ratio: float
    verified: bool
    version: int
    message: str


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = (color or "#000000").lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def safe_foreground(color: str) -> tuple[int, int, int]:
    """Màu module phải đủ tối so với nền trắng (tương phản >= 7:1), nếu không tự làm tối."""
    rgb = hex_to_rgb(color)
    white = (255, 255, 255)
    while contrast_ratio(rgb, white) < 7 and any(rgb):
        rgb = tuple(max(0, int(c * 0.85)) for c in rgb)
    return rgb


def _matrix(payload: str, with_logo: bool, mask: int | None = None) -> tuple[list[list[bool]], int]:
    qr = qrcode.QRCode(version=3 if with_logo else None,
                       error_correction=ERROR_CORRECT_H if with_logo else ERROR_CORRECT_M,
                       border=4, box_size=1, mask_pattern=mask)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.get_matrix(), qr.version


def _prepare_logo(logo: Image.Image, size: int) -> Image.Image:
    logo = logo.convert("RGBA")
    logo.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    canvas.paste(logo, ((size - logo.width) // 2, (size - logo.height) // 2), logo)
    return canvas


def render(payload: str, *, module_px: int = 12, fg: str = "#000000", logo: Image.Image | None = None,
           logo_ratio: float = DEFAULT_LOGO_RATIO, mask: int | None = None) -> tuple[Image.Image, int]:
    with_logo = logo is not None
    matrix, version = _matrix(payload, with_logo, mask)
    n = len(matrix)
    size = n * module_px
    color = safe_foreground(fg)
    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                draw.rectangle([x * module_px, y * module_px, (x + 1) * module_px - 1, (y + 1) * module_px - 1],
                               fill=color)
    if with_logo:
        ratio = max(MIN_LOGO_RATIO, min(MAX_LOGO_RATIO, logo_ratio))
        inner = n - 8  # cạnh vùng dữ liệu (bỏ viền tĩnh 4 module mỗi bên)
        pad_modules = max(3, int(round(inner * ratio)))
        if pad_modules % 2 != inner % 2:  # căn giữa đúng lưới module
            pad_modules += 1
        pad_px = pad_modules * module_px
        x0 = (size - pad_px) // 2
        # nền trắng che đúng các module -> logo không lẫn với module tối
        draw.rounded_rectangle([x0, x0, x0 + pad_px - 1, x0 + pad_px - 1], radius=module_px, fill="white")
        margin = max(2, module_px // 2)
        logo_img = _prepare_logo(logo, pad_px - 2 * margin)
        img.paste(logo_img, (x0 + margin, x0 + margin), logo_img)
    return img, version


# ---- Giải mã kiểm tra --------------------------------------------------------------
def _decode_cv2(img: Image.Image) -> list[str]:
    """Hai bộ dò của OpenCV lỗi ở những mã KHÁC nhau -> thử lần lượt cả hai.
    (Trên Streamlit Cloud không có ZBar, OpenCV là bộ giải mã duy nhất.)"""
    try:
        import cv2
    except Exception:
        return []
    arr = np.array(img.convert("RGB"))[:, :, ::-1].copy()
    factories = [cv2.QRCodeDetector] + ([cv2.QRCodeDetectorAruco] if hasattr(cv2, "QRCodeDetectorAruco") else [])
    for factory in factories:
        try:
            text, _, _ = factory().detectAndDecode(arr)
        except Exception:
            continue
        if text:
            return [text]
    return []


def _decode_zbar(img: Image.Image) -> list[str]:
    try:
        from pyzbar import pyzbar
    except Exception:
        return []
    try:
        return [r.data.decode("utf-8", "replace") for r in pyzbar.decode(img.convert("L"))]
    except Exception:
        return []


def decode(img: Image.Image) -> list[str]:
    out = _decode_cv2(img)
    for t in _decode_zbar(img):
        if t not in out:
            out.append(t)
    return out


def available_decoders() -> list[str]:
    names = []
    try:
        import cv2  # noqa: F401
        names.append("OpenCV")
    except Exception:
        pass
    try:
        from pyzbar import pyzbar  # noqa: F401
        pyzbar.decode(Image.new("L", (10, 10)))
        names.append("ZBar")
    except Exception:
        pass
    return names


def _variants(img: Image.Image):
    yield img
    w = img.width
    small = img.resize((max(120, w // 3), max(120, w // 3)), Image.BILINEAR)
    yield small.filter(ImageFilter.GaussianBlur(0.6))  # mô phỏng ảnh chụp nhỏ, hơi mờ
    big = Image.new("RGB", (int(w * 1.3), int(w * 1.3)), (235, 235, 235))  # thẻ trên nền xám
    big.paste(img, ((big.width - w) // 2, (big.height - w) // 2))
    yield big


def verify(img: Image.Image, expected: str) -> bool:
    """Mọi biến thể đều phải giải ra đúng nội dung (bởi ít nhất một bộ giải mã)."""
    if not available_decoders():
        return False
    return all(expected in decode(v) for v in _variants(img))


def make_qr(payload: str, *, logo: Image.Image | None = None, logo_ratio: float = DEFAULT_LOGO_RATIO,
            fg: str = "#000000", module_px: int = 12, check: bool = True) -> QrResult:
    """Dựng QR và tự kiểm tra giải mã. Không đạt thì lần lượt: đổi mẫu mặt nạ QR (cùng nội dung,
    khác hình ô), giảm kích thước logo, cuối cùng bỏ logo."""
    ratio = max(MIN_LOGO_RATIO, min(MAX_LOGO_RATIO, logo_ratio))
    if logo is not None:
        while ratio >= MIN_LOGO_RATIO - 1e-9:
            for mask in _MASK_ORDER:
                img, version = render(payload, module_px=module_px, fg=fg, logo=logo, logo_ratio=ratio, mask=mask)
                if not check:
                    return QrResult(img, payload, True, True, ratio, False, version, "QR có logo (chưa kiểm tra).")
                if verify(img, payload):
                    msg = "QR có logo – đã kiểm tra giải mã."
                    if ratio < logo_ratio - 1e-9:
                        msg = f"Logo được tự giảm còn {ratio:.0%} để bảo đảm quét được."
                    return QrResult(img, payload, True, True, ratio, True, version, msg)
            ratio = round(ratio - _STEP, 3)
    for mask in _MASK_ORDER:
        img, version = render(payload, module_px=module_px, fg=fg, mask=mask)
        ok = verify(img, payload) if check else False
        if ok or not check:
            break
    msg = "QR không logo." if logo is None else "Logo làm QR khó quét nên đã được bỏ để bảo đảm quét được."
    if check and not ok:
        msg = "CẢNH BÁO: không tự kiểm tra được QR (thiếu bộ giải mã hoặc màu quá nhạt)."
    return QrResult(img, payload, logo is not None, False, 0.0, ok, version, msg)


# None = mặt nạ tối ưu theo chuẩn; sau đó thử các mặt nạ còn lại nếu bộ giải mã kiểm tra gặp khó.
_MASK_ORDER = [None, 0, 1, 2, 3, 4, 5, 6, 7]


def to_png(img: Image.Image, dpi: int = 300) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(dpi, dpi), optimize=True)
    return buf.getvalue()
