"""Cấu hình ứng dụng.

Thứ tự ưu tiên: biến môi trường -> st.secrets -> giá trị mặc định.
Không bao giờ hardcode mật khẩu hoặc chuỗi kết nối thật trong mã nguồn.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT_DIR / "static" / "fonts"
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"

# Việt Nam không dùng giờ mùa hè -> múi giờ cố định UTC+7, không cần tzdata.
LOCAL_TZ = timezone(timedelta(hours=7), name="ICT")

# Tiền tố nội dung QR. Chỉ gồm ký tự "alphanumeric" của chuẩn QR để mã gọn hơn.
QR_PREFIX = "TNTT:"


def _from_streamlit_secrets(name: str):
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # không có secrets.toml hoặc chạy ngoài Streamlit
        pass
    return None


def get_setting(name: str, default=None):
    value = os.environ.get(name)
    if value is not None and value != "":
        return value
    value = _from_streamlit_secrets(name)
    if value is not None and value != "":
        return value
    return default


def get_bool(name: str, default: bool = False) -> bool:
    value = get_setting(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def database_url() -> str:
    url = get_setting("DATABASE_URL")
    if not url:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(DATA_DIR / 'tntt.db').as_posix()}"
    return normalize_url(str(url))


def normalize_url(url: str) -> str:
    """Supabase/Heroku hay đưa "postgres://" hoặc "postgresql://"; SQLAlchemy 2.1 mặc định
    driver psycopg v3 cho dạng này -> ép dùng psycopg2 (có trong requirements)."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def session_idle_minutes() -> int:
    try:
        return int(get_setting("SESSION_IDLE_MINUTES", 480))
    except (TypeError, ValueError):
        return 480


def face_module_allowed() -> bool:
    """Công tắc cấp triển khai. Mặc định TẮT; phải bật bằng secrets/env."""
    return get_bool("FACE_MODULE_ALLOWED", False)
