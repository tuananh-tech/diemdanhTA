"""Năm học, ngành, lớp."""
from __future__ import annotations

from datetime import date

import streamlit as st

from ...db import default_year_bounds as db_default_year
from ...services import org
from .. import state


def render() -> None:
    actor = state.actor()
    year = state.year()
    st.title("Ngành / Lớp")
    t1, t2, t3 = st.tabs(["🏫 Lớp", "🎨 Ngành", "📆 Năm học"], key="tabs_classes")
    with t1:
        _classes(actor, year)
    with t2:
        _branches(actor)
    with t3:
        _years(actor)


def _classes(actor, year) -> None:
    st.caption(f"Các lớp của năm học **{year.name}**. Mỗi năm học có danh sách lớp riêng để giữ lịch sử.")
    df = org.classes_frame(year.id)
    branches = {b.id: b.name for b in org.list_branches()}
    if not df.empty:
        st.dataframe(df.rename(columns={"name": "Lớp", "branch": "Ngành", "students": "Số em", "note": "Ghi chú"})
                     [["Lớp", "Ngành", "Số em", "Ghi chú"]], hide_index=True)
    c1, c2 = st.columns(2)
    with c1, st.form("new_class", clear_on_submit=True):
        st.markdown("**Thêm lớp**")
        name = st.text_input("Tên lớp", placeholder="Ví dụ: Ấu Nhi 1")
        branch = st.selectbox("Ngành", [None, *branches], format_func=lambda b: "—" if b is None else branches[b])
        order = st.number_input("Thứ tự hiển thị", 0, 999, 0)
        note = st.text_input("Ghi chú")
        if st.form_submit_button("Thêm lớp", type="primary"):
            with state.guard("Đã thêm lớp."):
                org.save_class(actor, year.id, name, branch, int(order), note or None)
                st.rerun()
    with c2:
        if df.empty:
            return
        st.markdown("**Sửa / xóa lớp**")
        ids = [int(i) for i in df.id]
        cid = st.selectbox("Chọn lớp", ids, format_func=lambda i: df[df.id == i].name.iloc[0])
        row = df[df.id == cid].iloc[0]
        with st.form(f"edit_class_{cid}"):
            name = st.text_input("Tên lớp", row["name"])
            bopts = [None, *branches]
            bval = int(row.branch_id) if row.branch_id == row.branch_id and row.branch_id is not None else None
            branch = st.selectbox("Ngành", bopts, index=bopts.index(bval) if bval in bopts else 0,
                                  format_func=lambda b: "—" if b is None else branches[b])
            order = st.number_input("Thứ tự", 0, 999, int(row.sort_order))
            note = st.text_input("Ghi chú", row.note or "")
            s1, s2 = st.columns(2)
            save = s1.form_submit_button("Lưu")
            delete = s2.form_submit_button("Xóa lớp")
        if save:
            with state.guard("Đã lưu."):
                org.save_class(actor, year.id, name, branch, int(order), note or None, class_id=cid)
                st.rerun()
        if delete:
            with state.guard("Đã xóa lớp."):
                org.delete_class(actor, cid)
                st.rerun()


def _branches(actor) -> None:
    branches = org.list_branches()
    for b in branches:
        with st.form(f"branch_{b.id}", border=True):
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1], vertical_alignment="bottom")
            name = c1.text_input("Tên ngành", b.name)
            color = c2.color_picker("Màu", b.color)
            order = c3.number_input("Thứ tự", 0, 99, b.sort_order)
            if c4.form_submit_button("Lưu"):
                with state.guard("Đã lưu."):
                    org.save_branch(actor, name, color, int(order), b.id)
                    st.rerun()
            if c5.form_submit_button("Xóa"):
                with state.guard("Đã xóa."):
                    org.delete_branch(actor, b.id)
                    st.rerun()
    with st.form("new_branch", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        name = c1.text_input("Ngành mới")
        color = c2.color_picker("Màu", "#1B2A4A")
        if c3.form_submit_button("Thêm ngành", type="primary"):
            with state.guard("Đã thêm."):
                org.save_branch(actor, name, color, len(branches))
                st.rerun()


def _years(actor) -> None:
    years = org.list_years()
    for y in years:
        with st.expander(f"{y.name}{' · hiện tại' if y.is_current else ''}"):
            with st.form(f"year_{y.id}"):
                name = st.text_input("Tên năm học", y.name)
                c1, c2, c3 = st.columns(3)
                start = c1.date_input("Bắt đầu", y.start_date, format="DD/MM/YYYY")
                end = c2.date_input("Kết thúc", y.end_date, format="DD/MM/YYYY")
                sem2 = c3.date_input("Bắt đầu học kỳ II", y.semester2_start, format="DD/MM/YYYY")
                current = st.checkbox("Đặt làm năm học hiện tại", y.is_current)
                if st.form_submit_button("Lưu"):
                    with state.guard("Đã lưu năm học."):
                        org.save_year(actor, name, start, end, sem2, current, y.id)
                        st.rerun()
    name, start, end, sem2 = db_default_year(date(date.today().year + 1, 9, 1))
    with st.form("new_year", border=True):
        st.markdown("**Tạo năm học mới**")
        n = st.text_input("Tên", name)
        c1, c2, c3 = st.columns(3)
        s = c1.date_input("Bắt đầu", start, format="DD/MM/YYYY")
        e = c2.date_input("Kết thúc", end, format="DD/MM/YYYY")
        h = c3.date_input("Bắt đầu học kỳ II", sem2, format="DD/MM/YYYY")
        cur = st.checkbox("Đặt làm năm học hiện tại")
        if st.form_submit_button("Tạo năm học", type="primary"):
            with state.guard("Đã tạo năm học. Hãy tạo lớp cho năm mới rồi dùng 'Chuyển năm học' ở trang Thiếu nhi."):
                org.save_year(actor, n, s, e, h, cur)
                st.rerun()
