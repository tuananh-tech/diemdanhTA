"""Cấu hình Xứ đoàn (tên, màu, năm học...) và logo.

Logo lưu trong bảng `assets` của CSDL (không lưu ra ổ đĩa) để không mất khi
Streamlit Cloud khởi động lại. Ảnh tải lên được kiểm tra, chuẩn hóa sang PNG.
"""
from __future__ import annotations

import io
import json
import threading
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from .. import config
from ..db import session_scope
from ..models import AppSetting, Asset
from ..security import P_SETTINGS, Actor
from . import audit

LOGO_XUDOAN = "logo_xudoan"
LOGO_PARISH = "logo_parish"
LOGO_KEYS = {LOGO_XUDOAN: "Logo Xứ đoàn", LOGO_PARISH: "Logo Giáo xứ"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_LOGO_PX = 1024

DEFAULTS: dict = {
    "parish_name": "Giáo xứ (chưa cấu hình)",
    "xudoan_name": "Xứ đoàn Thiếu Nhi Thánh Thể",
    "diocese": "",
    "motto": "",
    "primary_color": "#1B2A4A",
    "accent_color": "#D4A017",
    "logo_display_px": 64,
    "qr_use_logo": True,
    "qr_logo_source": LOGO_XUDOAN,
    "qr_logo_ratio": 0.24,
    "qr_color_mode": "brand",  # brand | bw
    "excused_counts_as_attended": False,
    "accept_plain_code_qr": False,
    "low_attendance_threshold": 75,
    "face_enabled": False,
    "face_threshold": 0.50,
    "face_margin": 0.06,
    "face_conditions_ack": [],
}

_cache_lock = threading.Lock()
_settings_cache: dict | None = None
_logo_cache: dict[str, tuple] = {}


def font(weight: str = "Regular", size: int = 24) -> ImageFont.FreeTypeFont:
    return _font(weight, size)


@lru_cache(maxsize=64)
def _font(weight: str, size: int):
    path = config.FONTS_DIR / f"BeVietnamPro-{weight}.ttf"
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)


# ---- Cấu hình --------------------------------------------------------------------
def get_settings(fresh: bool = False) -> dict:
    global _settings_cache
    with _cache_lock:
        if _settings_cache is not None and not fresh:
            return dict(_settings_cache)
    with session_scope() as s:
        rows = s.execute(select(AppSetting.key, AppSetting.value)).all()
    data = dict(DEFAULTS)
    for key, value in rows:
        try:
            data[key] = json.loads(value)
        except (TypeError, ValueError):
            continue
    with _cache_lock:
        _settings_cache = dict(data)
    return data


def invalidate() -> None:
    global _settings_cache
    with _cache_lock:
        _settings_cache = None
        _logo_cache.clear()


def save_settings(actor: Actor, values: dict) -> None:
    actor.require(P_SETTINGS)
    clean = {k: v for k, v in values.items() if k in DEFAULTS}
    for color_key in ("primary_color", "accent_color"):
        if color_key in clean and not _is_hex(clean[color_key]):
            raise ValueError("Màu phải ở dạng #RRGGBB.")
    if "qr_logo_ratio" in clean:
        clean["qr_logo_ratio"] = max(0.12, min(0.30, float(clean["qr_logo_ratio"])))
    with session_scope() as s:
        for key, value in clean.items():
            row = s.get(AppSetting, key)
            payload = json.dumps(value, ensure_ascii=False)
            if row is None:
                s.add(AppSetting(key=key, value=payload))
            else:
                row.value = payload
        audit.record(s, actor, "settings.update", "settings", None, keys=sorted(clean))
    invalidate()


def _is_hex(value) -> bool:
    v = str(value)
    return len(v) == 7 and v.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in v[1:])


# ---- Logo ------------------------------------------------------------------------
@dataclass
class LogoEdit:
    crop_left: float = 0.0  # tỷ lệ 0..0.45 cắt mỗi cạnh
    crop_top: float = 0.0
    crop_right: float = 0.0
    crop_bottom: float = 0.0
    square: bool = True
    padding: float = 0.04
    remove_white: bool = False
    rotate: int = 0


def load_upload(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Ảnh quá lớn (tối đa 5 MB).")
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        img = Image.open(io.BytesIO(data))
        if img.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Chỉ nhận PNG, JPG hoặc WebP.")
        if img.width * img.height > 25_000_000:
            raise ValueError("Ảnh có độ phân giải quá lớn.")
        img = ImageOps.exif_transpose(img)
        return img.convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("File không phải ảnh hợp lệ.") from exc


def process_logo(img: Image.Image, edit: LogoEdit) -> Image.Image:
    img = img.convert("RGBA")
    if edit.rotate:
        img = img.rotate(-edit.rotate, expand=True, fillcolor=(0, 0, 0, 0))
    w, h = img.size
    box = (int(w * edit.crop_left), int(h * edit.crop_top), int(w * (1 - edit.crop_right)), int(h * (1 - edit.crop_bottom)))
    if box[2] - box[0] < 16 or box[3] - box[1] < 16:
        raise ValueError("Vùng cắt quá nhỏ.")
    img = img.crop(box)
    if edit.remove_white:
        arr = img.load()
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = arr[x, y]
                if r > 242 and g > 242 and b > 242:
                    arr[x, y] = (r, g, b, 0)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    if edit.square:
        side = max(img.size)
        pad = int(side * edit.padding)
        canvas = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (255, 255, 255, 0))
        canvas.paste(img, ((canvas.width - img.width) // 2, (canvas.height - img.height) // 2), img)
        img = canvas
    img.thumbnail((MAX_LOGO_PX, MAX_LOGO_PX), Image.LANCZOS)
    return img


def save_logo(actor: Actor, key: str, img: Image.Image) -> None:
    actor.require(P_SETTINGS)
    if key not in LOGO_KEYS:
        raise ValueError("Loại logo không hợp lệ.")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    with session_scope() as s:
        row = s.get(Asset, key)
        if row is None:
            s.add(Asset(key=key, data=buf.getvalue(), mime="image/png", updated_by=actor.id))
        else:
            row.data, row.mime, row.updated_by = buf.getvalue(), "image/png", actor.id
        audit.record(s, actor, "settings.logo_upload", "asset", key, bytes=len(buf.getvalue()))
    invalidate()


def reset_logo(actor: Actor, key: str) -> None:
    actor.require(P_SETTINGS)
    with session_scope() as s:
        row = s.get(Asset, key)
        if row:
            s.delete(row)
        audit.record(s, actor, "settings.logo_reset", "asset", key)
    invalidate()


def logo_stamp(key: str) -> str:
    """Dấu phiên bản logo (đổi khi tải logo mới) – dùng làm khóa cache giao diện."""
    with session_scope() as s:
        row = s.execute(select(Asset.updated_at).where(Asset.key == key)).first()
    return row[0].isoformat() if row else "default"


def has_custom_logo(key: str) -> bool:
    with session_scope() as s:
        return s.get(Asset, key) is not None


def get_logo(key: str = LOGO_XUDOAN) -> Image.Image:
    """Logo đã cấu hình, hoặc logo mặc định. Luôn trả về ảnh RGBA."""
    with session_scope() as s:
        row = s.execute(select(Asset.updated_at).where(Asset.key == key)).first()
    stamp = row[0] if row else None
    with _cache_lock:
        cached = _logo_cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1].copy()
    if stamp is None:
        img = default_logo() if key == LOGO_XUDOAN else default_parish_logo()
    else:
        with session_scope() as s:
            data = s.get(Asset, key).data
        img = Image.open(io.BytesIO(data)).convert("RGBA")
    with _cache_lock:
        _logo_cache[key] = (stamp, img)
    return img.copy()


def logo_png(key: str = LOGO_XUDOAN, max_px: int = 256) -> bytes:
    img = get_logo(key)
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@lru_cache(maxsize=2)
def _default_logo_cached(primary: str = "#1B2A4A", accent: str = "#D4A017") -> Image.Image:
    """Biểu tượng mặc định trung tính (không mô phỏng huy hiệu chính thức)."""
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, size - 8, size - 8], fill=primary, outline=accent, width=18)
    d.ellipse([52, 52, size - 52, size - 52], outline=(255, 255, 255, 90), width=4)
    cx, top, bottom, w = size // 2, 92, 330, 42
    d.rounded_rectangle([cx - w // 2, top, cx + w // 2, bottom], radius=10, fill=accent)
    d.rounded_rectangle([cx - 105, 160, cx + 105, 160 + w], radius=10, fill=accent)
    f = _font("Bold", 58)
    text = "TNTT"
    tw = d.textlength(text, font=f)
    d.text((cx - tw / 2, 345), text, font=f, fill="white")
    return img


def default_logo() -> Image.Image:
    return _default_logo_cached().copy()


def default_parish_logo() -> Image.Image:
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, size - 8, size - 8], radius=96, fill="#FBF7EE", outline="#1B2A4A", width=16)
    cx = size // 2
    d.polygon([(cx, 90), (cx + 150, 210), (cx - 150, 210)], fill="#1B2A4A")
    d.rectangle([cx - 120, 210, cx + 120, 410], fill="#1B2A4A")
    d.rectangle([cx - 36, 300, cx + 36, 410], fill="#D4A017")
    d.rectangle([cx - 8, 30, cx + 8, 110], fill="#D4A017")
    d.rectangle([cx - 30, 52, cx + 30, 68], fill="#D4A017")
    return img
