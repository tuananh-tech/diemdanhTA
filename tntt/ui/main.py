"""Khởi tạo, xác thực và điều hướng theo quyền."""
from __future__ import annotations

import logging

import streamlit as st

from .. import db
from ..security import (
    P_AUDIT,
    P_ATTEND,
    P_CLASSES,
    P_QR,
    P_REPORTS,
    P_SESSIONS,
    P_SETTINGS,
    P_STUDENTS_VIEW,
    P_USERS,
)
from ..services import branding, org
from . import state, theme

log = logging.getLogger(__name__)


@st.cache_resource(show_spinner="Đang kết nối cơ sở dữ liệu…")
def _bootstrap() -> str:
    db.configure()
    db.init_db()
    return db.get_engine().dialect.name


def _startup_ok() -> bool:
    try:
        _bootstrap()
        return True
    except Exception:  # noqa: BLE001 - hiển thị hướng dẫn thay vì traceback
        log.exception("Không khởi tạo được CSDL")
        _bootstrap.clear()
        st.set_page_config(page_title="Điểm danh TNTT", page_icon="⛪", layout="centered")
        st.error("Không kết nối được cơ sở dữ liệu.")
        st.markdown(
            "- Kiểm tra `DATABASE_URL` trong **Secrets** (Streamlit Cloud) hoặc `.streamlit/secrets.toml`.\n"
            "- Với Supabase, dùng chuỗi **Session pooler** (cổng 5432) và thêm `?sslmode=require`.\n"
            "- Xem chi tiết lỗi trong log máy chủ (Manage app → Logs).\n"
            "\nKhông có dữ liệu nào bị ghi khi chưa kết nối được."
        )
        if st.button("Thử kết nối lại", type="primary"):
            st.rerun()
        return False


def _pages(actor):
    from .pages import (
        account,
        attendance_page,
        audit_page,
        classes_page,
        dashboard,
        qr_cards,
        reports_page,
        sessions_page,
        settings_page,
        students_page,
        users_page,
    )

    def P(fn, title, icon, url, perm=None, default=False):
        if perm and not actor.can(perm):
            return None
        page = st.Page(fn, title=title, icon=icon, url_path=url, default=default)
        state.PAGES[url] = page
        return page

    sections = {
        "Điểm danh": [
            P(dashboard.render, "Tổng quan", ":material/dashboard:", "tong-quan", default=True),
            P(attendance_page.render_manual, "Điểm danh", ":material/fact_check:", "diem-danh", P_ATTEND),
            P(attendance_page.render_scan, "Quét QR", ":material/qr_code_scanner:", "quet-qr", P_ATTEND),
            P(sessions_page.render, "Buổi sinh hoạt", ":material/event:", "buoi-sinh-hoat", P_SESSIONS),
        ],
        "Dữ liệu": [
            P(students_page.render, "Thiếu nhi", ":material/groups:", "thieu-nhi", P_STUDENTS_VIEW),
            P(classes_page.render, "Ngành / Lớp", ":material/account_tree:", "nganh-lop", P_CLASSES),
            P(qr_cards.render, "Thẻ QR", ":material/badge:", "the-qr", P_QR),
            P(reports_page.render, "Báo cáo", ":material/bar_chart:", "bao-cao", P_REPORTS),
        ],
        "Quản trị": [
            P(users_page.render, "Phân quyền", ":material/admin_panel_settings:", "phan-quyen", P_USERS),
            P(settings_page.render, "Cấu hình Xứ đoàn", ":material/church:", "cau-hinh", P_SETTINGS),
            P(audit_page.render, "Nhật ký hoạt động", ":material/history:", "nhat-ky", P_AUDIT),
        ],
        "Cá nhân": [P(account.render, "Tài khoản", ":material/person:", "tai-khoan")],
    }
    return {k: [p for p in v if p] for k, v in sections.items() if any(v)}


def _sidebar(actor):
    with st.sidebar:
        years = org.list_years()
        if years:
            ids = [y.id for y in years]
            current = state.year_id()
            chosen = st.selectbox("Năm học", ids, index=ids.index(current) if current in ids else 0,
                                  format_func=lambda i: next(y.name + (" (hiện tại)" if y.is_current else "")
                                                             for y in years if y.id == i))
            if chosen != current:
                st.session_state["year_id"] = chosen
                st.rerun()
        st.caption(f"👤 {actor.full_name} · {actor.username}")
        if st.button("Đăng xuất", icon=":material/logout:", width="stretch"):
            from ..services import audit

            audit.log(actor, "auth.logout", "user", actor.id)
            state.logout()
            st.rerun()


def run() -> None:
    if not _startup_ok():
        return
    settings = branding.get_settings()
    st.set_page_config(page_title=f"Điểm danh · {settings['xudoan_name']}",
                       page_icon=branding.get_logo().resize((64, 64)), layout="wide",
                       initial_sidebar_state="auto")
    theme.inject_css()
    st.logo(branding.get_logo().resize((256, 256)), size="large")

    actor = state.current_actor()
    state.apply_cookie_op()
    if actor is None:
        from .pages import login

        login.render()
        return
    st.session_state["_actor"] = actor

    if st.session_state.get("must_change_password"):
        from .pages import account

        theme.header(actor)
        st.warning("Vì lý do an toàn, bạn cần đổi mật khẩu trước khi sử dụng hệ thống.")
        account.change_password_form(actor, forced=True)
        return

    year = state.year()
    nav = st.navigation(_pages(actor))
    _sidebar(actor)
    theme.header(actor, year.name if year else None)
    state.show_flash()
    nav.run()
