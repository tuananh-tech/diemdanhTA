from datetime import date

import pytest

from tntt import constants as C
from tntt.security import Actor, hash_password, password_problems, verify_password
from tntt.textutil import normalize_code, parse_date, search_key, split_saint_name, strip_accents


def test_strip_accents_and_search_key():
    assert strip_accents("Đặng Thị Ánh Tuyết") == "Dang Thi Anh Tuyet"
    assert search_key("  Nguyễn   Văn  Đức ") == "nguyen van duc"


@pytest.mark.parametrize("full,expected", [
    ("Maria Cao Nguyễn Hoàng Châu", ("Maria", "Cao Nguyễn Hoàng Châu")),
    ("Giuse Maria Hoàng Mạnh Đức", ("Giuse Maria", "Hoàng Mạnh Đức")),
    ("Phanxico Savie Trần Minh Khôi", ("Phanxico Savie", "Trần Minh Khôi")),
    ("Bùi Tiến Nguyên", ("", "Bùi Tiến Nguyên")),
    ("Maria An", ("", "Maria An")),  # quá ngắn -> không tách
])
def test_split_saint_name(full, expected):
    assert split_saint_name(full) == expected


@pytest.mark.parametrize("raw,expected", [
    ("15/08/2014", date(2014, 8, 15)), ("2014-08-15", date(2014, 8, 15)),
    ("2014-08-15 00:00:00", date(2014, 8, 15)), ("41866", date(2014, 8, 15)), ("", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("32/13/2014")


def test_normalize_code_keeps_leading_zero():
    assert normalize_code("0012") == "0012"
    assert normalize_code("12.0") == "12"
    assert normalize_code(" tn01 ") == "TN01"


def test_database_url_normalization():
    from tntt.config import normalize_url

    assert normalize_url("postgres://u:p@h:5432/d") == "postgresql+psycopg2://u:p@h:5432/d"
    assert normalize_url(" postgresql://u@h/d?sslmode=require") == "postgresql+psycopg2://u@h/d?sslmode=require"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_password_hashing():
    h = hash_password("Secret123")
    assert verify_password("Secret123", h)
    assert not verify_password("secret123", h)
    assert "Secret123" not in h
    assert password_problems("short")
    assert not password_problems("LongEnough1")


def test_role_permissions():
    viewer = Actor(1, "v", "V", C.ROLE_VIEWER)
    assert viewer.can("reports.view") and not viewer.can("attendance.mark")
    assert Actor(1, "a", "A", C.ROLE_ADMIN).can("users.manage")
    assert not Actor(1, "c", "C", C.ROLE_COORDINATOR).can("users.manage")
