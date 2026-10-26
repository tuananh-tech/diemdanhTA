"""Buổi sinh hoạt: danh sách, tạo đơn lẻ / theo lịch, mở, đóng, chốt."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import streamlit as st

from ... import constants as C
from ...security import P_ATTEND_CLOSED
from ...services import attendance, org, sessions, users
from .. import state

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]


def render() -> None:
    actor = state.actor()
    year = state.year()
    st.title("Buổi sinh hoạt")
    tab_list, tab_new, tab_sched = st.tabs(["📅 Danh sách buổi", "➕ Tạo buổi", "🗓️ Tạo theo lịch"], key="tabs_sessions")
    with tab_new:
        _create_single(actor, year)
    with tab_sched:
        _create_recurring(actor, year)
    with tab_list:
        _list(actor, year)


def _class_inputs(actor, year, key: str):
    opts = org.class_options(year.id, actor)
    scope_all = st.toggle("Toàn Xứ đoàn (mọi thiếu nhi đang sinh hoạt)", key=f"all_{key}", disabled=not actor.is_global,
                          help="Chỉ Ban Điều hành tạo được buổi cho toàn Xứ đoàn.")
    class_ids = []
    if not scope_all:
        branches = org.list_branches()
        cdf = org.classes_frame(year.id, actor)
        pick_branch = st.multiselect("Chọn nhanh theo ngành", [b.id for b in branches],
                                     format_func=lambda b: next(x.name for x in branches if x.id == b), key=f"br_{key}")
        preset = [int(c) for c in cdf[cdf.branch_id.isin(pick_branch)].id] if pick_branch else []
        class_ids = st.multiselect("Lớp tham dự", list(opts), default=[c for c in preset if c in opts],
                                   format_func=opts.get, key=f"cls_{key}_{'-'.join(map(str, pick_branch))}")
    return scope_all, class_ids


def _create_single(actor, year) -> None:
    owners = users.user_options()
    scope_all, class_ids = _class_inputs(actor, year, "single")
    with st.form("new_session"):
        c1, c2 = st.columns(2)
        activity = c1.selectbox("Loại sinh hoạt", C.ACTIVITY_TYPES)
        title = c2.text_input("Tên buổi (để trống sẽ tự đặt)", max_chars=150)
        c3, c4, c5 = st.columns(3)
        d = c3.date_input("Ngày", value=attendance.now_local().date(), format="DD/MM/YYYY")
        start = c4.time_input("Giờ bắt đầu", value=time(8, 0), step=300)
        late = c5.number_input("Tính trễ sau (phút)", 0, 180, 15, step=5, help="0 = không tính trễ")
        owner = st.selectbox("Người phụ trách", list(owners), format_func=owners.get,
                             index=list(owners).index(actor.id) if actor.id in owners else 0)
        note = st.text_input("Ghi chú", max_chars=255)
        open_now = st.checkbox("Mở phiên ngay (lập danh sách tham dự)", value=d <= attendance.now_local().date())
        ok = st.form_submit_button("Tạo buổi", type="primary")
    if ok:
        with state.guard():
            late_after = (datetime.combine(d, start) + timedelta(minutes=int(late))).time() if late else None
            sid = sessions.create_session(actor, year_id=year.id, title=title, activity_type=activity, session_date=d,
                                          start_time=start, late_after=late_after, class_ids=class_ids,
                                          scope_all=scope_all, owner_id=owner, note=note or None, open_now=open_now)
            st.session_state["active_session_id"] = sid
            state.flash("success", "Đã tạo buổi sinh hoạt.")
            st.rerun()


def _create_recurring(actor, year) -> None:
    st.caption("Ví dụ: tạo tất cả buổi Thánh lễ Chủ nhật 7:00 trong học kỳ. Buổi tương lai ở trạng thái "
               "**Đã lên lịch**; danh sách tham dự được lập khi mở phiên (dùng dữ liệu lớp mới nhất).")
    scope_all, class_ids = _class_inputs(actor, year, "rec")
    with st.form("recurring"):
        c1, c2 = st.columns(2)
        activity = c1.selectbox("Loại sinh hoạt", C.ACTIVITY_TYPES, key="rec_act")
        prefix = c2.text_input("Tiền tố tên buổi", placeholder="Ví dụ: Thánh lễ thiếu nhi")
        today = attendance.now_local().date()
        c3, c4 = st.columns(2)
        start = c3.date_input("Từ ngày", value=max(today, year.start_date), format="DD/MM/YYYY")
        end = c4.date_input("Đến ngày", value=min(year.end_date, max(today, year.start_date) + timedelta(days=90)),
                            format="DD/MM/YYYY")
        days = st.multiselect("Các thứ trong tuần", list(range(7)), default=[6], format_func=lambda i: WEEKDAYS[i])
        c5, c6 = st.columns(2)
        t = c5.time_input("Giờ bắt đầu", value=time(7, 0), step=300, key="rec_t")
        late = c6.number_input("Tính trễ sau (phút)", 0, 180, 10, step=5, key="rec_late")
        ok = st.form_submit_button("Tạo các buổi theo lịch", type="primary")
    if ok:
        with state.guard():
            res = sessions.create_recurring(actor, year_id=year.id, start=start, end=end, weekdays=days,
                                            activity_type=activity, start_time=t, late_minutes=int(late) or None,
                                            class_ids=class_ids, scope_all=scope_all, title_prefix=prefix or None)
            state.flash("success", f"Đã tạo {res['created']} buổi, bỏ qua {res['skipped']} buổi đã tồn tại.")
            st.rerun()


def _list(actor, year) -> None:
    today = attendance.now_local().date()
    c1, c2 = st.columns([2, 1])
    rng = c1.date_input("Khoảng ngày", (today - timedelta(days=30), today + timedelta(days=30)), format="DD/MM/YYYY")
    status = c2.selectbox("Trạng thái", [None, *C.SESSION_STATUS_LABELS],
                          format_func=lambda s: "Tất cả" if s is None else C.SESSION_STATUS_LABELS[s])
    if not isinstance(rng, (tuple, list)) or len(rng) != 2:
        return
    df = sessions.list_sessions(year.id, actor, date_from=rng[0], date_to=rng[1], status=status)
    if df.empty:
        st.info("Không có buổi nào trong khoảng đã chọn.")
        return
    view = df.assign(
        Ngày=df.session_date.map(lambda d: d.strftime("%d/%m/%Y")),
        Giờ=df.start_time.map(lambda t: t.strftime("%H:%M") if t else ""),
        TrangThai=df.status.map(C.SESSION_STATUS_LABELS),
        TienDo=[f"{m}/{e}" for m, e in zip(df.marked, df.eligible)],
    )[["Ngày", "Giờ", "title", "activity_type", "classes", "TrangThai", "TienDo", "owner"]]
    view.columns = ["Ngày", "Giờ", "Tên buổi", "Loại", "Đối tượng", "Trạng thái", "Đã điểm danh", "Phụ trách"]
    event = st.dataframe(view, hide_index=True, on_select="rerun", selection_mode="single-row", key="sess_table")
    rows = event.selection.rows if event and event.selection else []
    if not rows:
        st.caption("Chọn một dòng để mở / đóng / chỉnh sửa buổi.")
        return
    _detail(actor, sessions.get_session(int(df.iloc[rows[0]].id)))


def _detail(actor, sess) -> None:
    with st.container(border=True):
        st.subheader(sess.title)
        counts = attendance.session_counts(sess.id)
        st.caption(f"{C.SESSION_STATUS_LABELS[sess.status]} · {counts['total']} em thuộc đối tượng · "
                   f"chưa điểm danh {counts[C.UNMARKED]} · mã phiên `{sess.uid}`")
        b1, b2, b3, b4 = st.columns(4)
        if sess.status == C.SESSION_SCHEDULED and b1.button("▶️ Mở phiên", type="primary"):
            with state.guard():
                res = sessions.open_session(actor, sess.id)
                state.flash("success", f"Đã mở phiên, danh sách {res['added']} em.")
                st.rerun()
        if sess.status == C.SESSION_OPEN:
            if b1.button("🔄 Đồng bộ danh sách", help="Thêm em mới vào lớp; gỡ em đã chuyển lớp mà chưa được điểm danh"):
                with state.guard():
                    res = sessions.sync_roster(actor, sess.id)
                    state.flash("success", f"Thêm {res['added']} em, gỡ {res['removed']} em.")
                    st.rerun()
            if b2.button("📋 Đi tới điểm danh"):
                st.session_state["active_session_id"] = sess.id
                state.go_to("diem-danh")
        if sess.status == C.SESSION_CLOSED and actor.can(P_ATTEND_CLOSED) and b1.button("🔓 Mở lại phiên"):
            with state.guard():
                sessions.reopen_session(actor, sess.id)
                st.rerun()
        if sess.status == C.SESSION_OPEN:
            with b3.popover("🔒 Đóng phiên"):
                st.write(f"Còn **{counts[C.UNMARKED]}** em chưa điểm danh.")
                how = st.radio("Xử lý các em chưa điểm danh", ["keep", C.ABSENT, C.EXCUSED],
                               format_func={"keep": "Giữ nguyên 'Chưa điểm danh'", C.ABSENT: "Chốt là Vắng không phép",
                                            C.EXCUSED: "Chốt là Vắng có phép"}.get)
                if st.button("Xác nhận đóng phiên", type="primary"):
                    with state.guard():
                        n = sessions.close_session(actor, sess.id, None if how == "keep" else how)
                        state.flash("success", f"Đã đóng phiên. Chốt {n} em.")
                        st.rerun()
        with b4.popover("🗑️ Xóa"):
            st.warning("Xóa buổi sẽ xóa toàn bộ dữ liệu điểm danh của buổi này.")
            if st.button("Xóa vĩnh viễn", type="primary", key="del_sess"):
                with state.guard():
                    sessions.delete_session(actor, sess.id)
                    state.flash("success", "Đã xóa buổi.")
                    st.rerun()
        with st.expander("✏️ Sửa thông tin buổi"):
            owners = users.user_options()
            with st.form(f"edit_{sess.id}"):
                title = st.text_input("Tên buổi", sess.title, max_chars=150)
                activity = st.selectbox("Loại", C.ACTIVITY_TYPES, index=C.ACTIVITY_TYPES.index(sess.activity_type)
                                        if sess.activity_type in C.ACTIVITY_TYPES else 0)
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Ngày", sess.session_date, format="DD/MM/YYYY")
                t = c2.time_input("Giờ bắt đầu", sess.start_time or time(8, 0), step=300)
                late = c3.time_input("Mốc tính trễ", sess.late_after or time(8, 15), step=300)
                owner = st.selectbox("Phụ trách", list(owners), format_func=owners.get,
                                     index=list(owners).index(sess.owner_id) if sess.owner_id in owners else 0)
                note = st.text_input("Ghi chú", sess.note or "", max_chars=255)
                if st.form_submit_button("Lưu"):
                    with state.guard():
                        sessions.update_session(actor, sess.id, title=title, activity_type=activity, session_date=d,
                                                start_time=t, late_after=late, owner_id=owner, note=note or None)
                        state.flash("success", "Đã lưu.")
                        st.rerun()


