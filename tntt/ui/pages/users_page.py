"""Phân quyền: tài khoản, vai trò, phạm vi lớp/ngành."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import constants as C
from ...security import ROLE_PERMISSIONS, generate_password
from ...services import org, users
from .. import state

PERM_LABELS = {
    "users.manage": "Quản lý tài khoản", "settings.manage": "Cấu hình Xứ đoàn", "backup.manage": "Sao lưu/khôi phục",
    "audit.view": "Xem nhật ký", "students.view": "Xem thiếu nhi", "students.edit": "Sửa thiếu nhi",
    "students.import": "Nhập Excel", "classes.manage": "Quản lý ngành/lớp/năm học", "sessions.manage": "Tạo/đóng buổi",
    "attendance.mark": "Điểm danh", "attendance.edit_closed": "Sửa buổi đã đóng", "reports.view": "Xem báo cáo",
    "qr.manage": "Thẻ QR", "face.manage": "Module khuôn mặt",
}


def render() -> None:
    actor = state.actor()
    year = state.year()
    st.title("Phân quyền")
    with st.expander("Bảng quyền theo vai trò"):
        st.dataframe(pd.DataFrame({C.ROLE_LABELS[r]: ["✓" if p in perms else "" for p in PERM_LABELS]
                                   for r, perms in ROLE_PERMISSIONS.items()}, index=list(PERM_LABELS.values())))
        st.caption("Huynh trưởng và Người xem chỉ thấy dữ liệu của các lớp/ngành được phân công. Phân công theo NGÀNH "
                   "tự áp dụng sang năm học mới; phân công theo LỚP gắn với lớp của từng năm.")
    df = users.list_users()
    branches = {b.id: b.name for b in org.list_branches()}
    copts = org.class_options(year.id)
    if not df.empty:
        st.dataframe(pd.DataFrame({
            "Tên đăng nhập": df.username, "Họ tên": df.full_name, "Vai trò": df.role.map(C.ROLE_LABELS),
            "Phạm vi": df.scopes.replace("", "Toàn bộ / chưa phân công"),
            "Hoạt động": df.is_active.map(lambda v: "✓" if v else "Đã khóa"),
            "Tạm khóa": df.locked.map(lambda v: "🔒" if v else ""),
            "Đăng nhập gần nhất": df.last_login_at.map(lambda d: d.strftime("%d/%m/%Y %H:%M") if pd.notna(d) else ""),
        }), hide_index=True)

    t1, t2 = st.tabs(["➕ Tạo tài khoản", "✏️ Sửa tài khoản"], key="tabs_users")
    with t1, st.form("new_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        username = c1.text_input("Tên đăng nhập", placeholder="vd: ht.giuse")
        full_name = c2.text_input("Họ tên")
        role = st.selectbox("Vai trò", list(C.ROLE_LABELS), index=2, format_func=C.ROLE_LABELS.get)
        b = st.multiselect("Phụ trách ngành", list(branches), format_func=branches.get)
        c = st.multiselect(f"Phụ trách lớp (năm {year.name})", list(copts), format_func=copts.get)
        suggested = st.session_state.setdefault("suggested_pw", generate_password())
        pw = st.text_input("Mật khẩu tạm (người dùng phải đổi khi đăng nhập lần đầu)", value=suggested)
        if st.form_submit_button("Tạo tài khoản", type="primary"):
            with state.guard():
                users.create_user(actor, username, full_name, role, pw, b, c)
                st.session_state.pop("suggested_pw", None)
                state.flash("success", f"Đã tạo tài khoản **{username}**. Mật khẩu tạm: `{pw}` – hãy gửi riêng cho người dùng.")
                st.rerun()
    with t2:
        if df.empty:
            return
        uid = st.selectbox("Tài khoản", [int(i) for i in df.id],
                           format_func=lambda i: f"{df[df.id == i].full_name.iloc[0]} ({df[df.id == i].username.iloc[0]})")
        row = df[df.id == uid].iloc[0]
        with st.form(f"edit_user_{uid}"):
            full_name = st.text_input("Họ tên", row.full_name)
            roles = list(C.ROLE_LABELS)
            role = st.selectbox("Vai trò", roles, index=roles.index(row.role), format_func=C.ROLE_LABELS.get)
            b = st.multiselect("Phụ trách ngành", list(branches), default=[x for x in row.branch_ids if x in branches],
                               format_func=branches.get)
            all_classes = org.class_options(year.id)
            other_year_classes = [x for x in row.class_ids if x not in all_classes]
            c = st.multiselect(f"Phụ trách lớp (năm {year.name})", list(all_classes),
                               default=[x for x in row.class_ids if x in all_classes], format_func=all_classes.get)
            active = st.checkbox("Đang hoạt động", bool(row.is_active))
            if st.form_submit_button("Lưu thay đổi", type="primary"):
                with state.guard():
                    users.update_user(actor, uid, full_name=full_name, role=role, is_active=active, branch_ids=b,
                                      class_ids=c + other_year_classes)
                    state.flash("success", "Đã cập nhật tài khoản.")
                    st.rerun()
        c1, c2 = st.columns(2)
        with c1.popover("🔑 Đặt lại mật khẩu"):
            newpw = st.text_input("Mật khẩu mới", value=generate_password(), key=f"rp_{uid}")
            if st.button("Đặt lại", key=f"rpb_{uid}", type="primary"):
                with state.guard(f"Đã đặt lại. Mật khẩu tạm: {newpw}"):
                    users.reset_password(actor, uid, newpw)
                    st.code(newpw)
        if row.locked and c2.button("🔓 Mở khóa đăng nhập"):
            with state.guard("Đã mở khóa."):
                users.unlock_user(actor, uid)
                st.rerun()
