"""Tiện ích kiểm thử giao diện bằng Playwright (chạy với server Streamlit thật)."""
from __future__ import annotations


import time
from pathlib import Path

from playwright.sync_api import Page

BASE = "http://localhost:8599"
OUT = Path(__file__).resolve().parents[2] / "test-artifacts"
OUT.mkdir(exist_ok=True)


def wait_idle(page: Page, timeout: float = 20) -> None:
    """Chờ Streamlit chạy xong (không còn trạng thái 'running')."""
    end = time.time() + timeout
    page.wait_for_timeout(900)
    calm = 0
    while time.time() < end:
        busy = page.locator("[data-testid='stStatusWidget']").count() > 0 or \
            page.locator("[data-testid='stSpinner']").count() > 0
        calm = 0 if busy else calm + 1
        if calm >= 3:
            return
        page.wait_for_timeout(250)


def shot(page: Page, name: str, full: bool = True) -> Path:
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    return path


def fill(page: Page, label: str, value: str, nth: int = 0) -> None:
    page.get_by_label(label, exact=True).nth(nth).fill(value)


def login(page: Page, username: str, password: str) -> None:
    page.goto(BASE)
    page.get_by_label("Tên đăng nhập", exact=True).wait_for(timeout=30000)
    fill(page, "Tên đăng nhập", username)
    fill(page, "Mật khẩu", password)
    page.get_by_role("button", name="Đăng nhập", exact=True).click()
    wait_idle(page)
