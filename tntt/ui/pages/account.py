"""Tài khoản cá nhân: thông tin, đổi mật khẩu."""
from __future__ import annotations

import streamlit as st

from ... import constants as C
from ...services import users
from .. import state


def change_password_form(actor, forced: bool = False) -> None:
    with st.form("change_pw", border=True):
        st.subheader("Đổi mật khẩu")
        old = st.text_input("Mật khẩu hiện tại", type="password", autocomplete="current-password")
        new1 = st.text_input("Mật khẩu mới (≥ 8 ký tự, có chữ và số)", type="password", autocomplete="new-password")
        new2 = st.text_input("Nhập lại mật khẩu mới", type="password", autocomplete="new-password")
        ok = st.form_submit_button("Lưu mật khẩu mới", type="primary")
    if ok:
        if new1 != new2:
            st.error("Hai mật khẩu mới không khớp.")
            return
        with state.guard():
            users.change_password(actor, old, new1)
            st.session_state["must_change_password"] = False
            state.flash("success", "Đã đổi mật khẩu.")
            st.rerun()
    if forced and st.button("Đăng xuất"):
        state.logout()
        st.rerun()


def render() -> None:
    actor = state.actor()
    st.title("Tài khoản của tôi")
    st.markdown(f"**{actor.full_name}** · `{actor.username}` · {C.ROLE_LABELS[actor.role]}")
    if not actor.is_global:
        from ...services import org

        opts = org.class_options(state.year_id(), actor)
        st.caption("Phạm vi phụ trách năm học đang chọn: " + (", ".join(opts.values()) or "chưa được phân công lớp"))
    change_password_form(actor)
