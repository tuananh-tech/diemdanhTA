"""Đăng nhập và khởi tạo tài khoản quản trị đầu tiên."""
from __future__ import annotations

import html
import time

import streamlit as st

from ...services import branding, users
from .. import state, theme


def _brand_block():
    s = branding.get_settings()
    st.html(f"""
<div style="text-align:center;margin:12px 0 18px">
  <img src="{theme.logo_data_uri(px=220)}" alt="Logo" style="width:110px;height:110px;object-fit:contain">
  <div style="font-weight:700;font-size:1.35rem;color:var(--tn-navy);margin-top:8px">{html.escape(s['xudoan_name'])}</div>
  <div style="color:#8A6A10;font-size:.92rem">{html.escape(s['parish_name'])}</div>
  <div class="tn-muted" style="margin-top:4px">Hệ thống điểm danh Thiếu Nhi Thánh Thể</div>
</div>""")


def render() -> None:
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        _brand_block()
        state.show_flash()
        if not users.has_users():
            _setup_form()
        else:
            _login_form()


def _login_form() -> None:
    # Hạn chế dò mật khẩu trong cùng một phiên trình duyệt (khóa tài khoản xử lý ở tầng dịch vụ).
    wait = st.session_state.get("login_wait_until", 0) - time.time()
    with st.form("login", border=True):
        st.subheader("Đăng nhập")
        username = st.text_input("Tên đăng nhập", autocomplete="username")
        password = st.text_input("Mật khẩu", type="password", autocomplete="current-password")
        remember = st.checkbox("Ghi nhớ đăng nhập trên thiết bị này", value=True,
                               help="Bỏ chọn nếu dùng máy chung. Tự hết hạn khi không hoạt động.")
        submitted = st.form_submit_button("Đăng nhập", type="primary", width="stretch")
    if submitted:
        if wait > 0:
            st.error(f"Vui lòng chờ {int(wait) + 1} giây rồi thử lại.")
            return
        res = users.authenticate(username, password)
        if res.ok:
            st.session_state.pop("login_fail", None)
            state.login(res.actor, res.must_change_password, remember=remember)
            st.rerun()
        fails = st.session_state.get("login_fail", 0) + 1
        st.session_state["login_fail"] = fails
        if fails >= 3:
            st.session_state["login_wait_until"] = time.time() + min(60, 5 * 2 ** (fails - 3))
        st.error(res.message)
    st.caption("Quên mật khẩu? Liên hệ quản trị viên Xứ đoàn để được đặt lại.")


def _setup_form() -> None:
    st.info("**Khởi tạo hệ thống** – tạo tài khoản quản trị đầu tiên.\n\n"
            "Cần **mã khởi tạo (setup token)**: lấy trong `SETUP_TOKEN` của Secrets, hoặc trong log máy chủ / "
            "file `data/SETUP_TOKEN.txt` khi chạy trên máy.")
    users.setup_token()  # sinh & ghi log nếu chưa cấu hình
    with st.form("setup", border=True):
        token = st.text_input("Mã khởi tạo", type="password")
        full_name = st.text_input("Họ tên quản trị viên")
        username = st.text_input("Tên đăng nhập", value="admin")
        p1 = st.text_input("Mật khẩu (≥ 8 ký tự, có chữ và số)", type="password")
        p2 = st.text_input("Nhập lại mật khẩu", type="password")
        ok = st.form_submit_button("Tạo tài khoản quản trị", type="primary", width="stretch")
    if ok:
        if p1 != p2:
            st.error("Hai mật khẩu không khớp.")
            return
        with state.guard():
            actor = users.create_first_admin(token, username, full_name, p1)
            state.login(actor, False)
            state.flash("success", "Đã tạo tài khoản quản trị. Hãy vào **Cấu hình Xứ đoàn** để nhập tên và logo.")
            st.rerun()
