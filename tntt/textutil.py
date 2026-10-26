"""Tiện ích văn bản tiếng Việt: bỏ dấu, chuẩn hóa tên, tách Tên Thánh, đọc ngày."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

_SPACES = re.compile(r"\s+")


def strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.replace("đ", "d").replace("Đ", "D")


def search_key(*parts: str | None) -> str:
    """Chuỗi tìm kiếm không dấu, chữ thường."""
    joined = " ".join(p for p in parts if p)
    return _SPACES.sub(" ", strip_accents(joined).lower()).strip()


def clean_name(value: str | None) -> str:
    value = unicodedata.normalize("NFC", str(value or ""))
    return _SPACES.sub(" ", value).strip()


def title_name(value: str | None) -> str:
    """'nguyễn văn AN' -> 'Nguyễn Văn An' (giữ nguyên nếu đã viết đúng)."""
    value = clean_name(value)
    return " ".join(w[:1].upper() + w[1:].lower() for w in value.split(" ")) if value else ""


# Tên Thánh phổ biến (dạng viết thường không dấu, ghép nhiều từ để ưu tiên khớp dài).
_SAINTS = [
    "giuse maria", "phanxico xavie", "phanxico savie", "phanxico assisi", "maria goretti",
    "maria magdalena", "gioan baotixita", "gioan boscô", "gioan bosco", "gioan phaolo",
    "anton padua", "teresa calcutta", "phero", "phêrô", "phaolo", "giuse", "maria", "anna", "teresa",
    "cecilia", "vincente", "vinh son", "vinhson", "phanxico", "anton", "antôn", "anre", "andre",
    "anrê", "gioan", "giacobe", "giacôbê", "luca", "marco", "matheu", "mattheu", "tôma", "toma",
    "micae", "micaen", "raphael", "gabriel", "dominico", "đaminh", "daminh", "augustino", "agustino",
    "phanxica", "rosa", "lucia", "agata", "agnes", "catarina", "monica", "elizabeth", "isave",
    "martino", "simon", "stephano", "têphanô", "tephano", "bênađô", "benado", "louis", "luy",
    "phillipphe", "philipphe", "philiphe", "barnaba", "batolomeo", "tadeo", "gioakim", "clara",
    "veronica", "faustina", "inhaxio", "alphonso", "anphongso", "giuliana", "isidore", "kim",
]
_SAINT_KEYS = sorted({search_key(s) for s in _SAINTS}, key=lambda s: -len(s.split()))


def split_saint_name(full: str) -> tuple[str, str]:
    """Tách 'Maria Nguyễn Thị A' -> ('Maria', 'Nguyễn Thị A'). Không chắc -> ('', full)."""
    full = clean_name(full)
    words = full.split(" ")
    keys = search_key(full).split(" ")
    for saint in _SAINT_KEYS:
        n = len(saint.split(" "))
        if len(words) > n + 1 and " ".join(keys[:n]) == saint:
            return " ".join(words[:n]), " ".join(words[n:])
    return "", full


_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%y", "%m/%d/%Y"]


def parse_date(value) -> date | None:
    """Đọc ngày từ chuỗi/Excel. Ưu tiên định dạng Việt Nam dd/mm/yyyy. Lỗi -> ValueError."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    # "2015-03-02 00:00:00" (pandas/openpyxl) -> lấy phần ngày
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?", text):
        text = text[:10]
    # Số serial của Excel
    if re.fullmatch(r"\d{4,5}(\.0+)?", text):
        serial = int(float(text))
        if 1000 < serial < 80000:
            return date(1899, 12, 30) + timedelta(days=serial)
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
            if 1900 <= parsed.year <= 2100:
                return parsed
        except ValueError:
            continue
    raise ValueError(f"Không đọc được ngày: '{value}'")


def normalize_code(value) -> str:
    """Mã thiếu nhi luôn là chuỗi, giữ số 0 ở đầu, bỏ đuôi '.0' do Excel."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    return text.upper()
