"""Tổng quan: chỉ số chính, phiên đang mở (tự làm mới), biểu đồ, cảnh báo chuyên cần."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from ... import constants as C
from ...security import P_REPORTS
from ...services import attendance, branding, org, reports, sessions, students
from .. import charts, state, theme
from ..state import go_to

CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"], "responsive": True}


def render() -> None:
    actor = state.actor()
    year = state.year()
    if year is None:
        st.warning("Chưa có năm học. Vào **Ngành / Lớp** để tạo năm học.")
        return
    settings = branding.get_settings()
    st.title("Tổng quan")
    _today_panel(actor, year)
    if not actor.can(P_REPORTS):
        return

    today = attendance.now_local().date()
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.6, 1, 1, 1])
        start, end = year.start_date, min(today, year.end_date) if today >= year.start_date else year.end_date
        rng = c1.date_input("Khoảng thời gian", (max(start, end - timedelta(days=90)), end),
                            min_value=year.start_date, max_value=year.end_date, format="DD/MM/YYYY")
        branches = {b.id: b.name for b in org.list_branches()}
        branch = c2.selectbox("Ngành", [None, *branches], format_func=lambda b: "Tất cả" if b is None else branches[b])
        copts = org.class_options(year.id, actor)
        if branch:
            cdf = org.classes_frame(year.id, actor)
            copts = {k: v for k, v in copts.items() if k in set(cdf[cdf.branch_id == branch].id)}
        cls = c3.selectbox("Lớp", [None, *copts], format_func=lambda c: "Tất cả" if c is None else copts[c])
        activity = c4.selectbox("Loại sinh hoạt", [None, *C.ACTIVITY_TYPES], format_func=lambda a: a or "Tất cả")
    if not isinstance(rng, (tuple, list)) or len(rng) != 2:
        st.info("Chọn đủ ngày bắt đầu và kết thúc.")
        return
    df = reports.attendance_frame(year.id, actor, date_from=rng[0], date_to=rng[1], branch_id=branch, class_id=cls,
                                  activity_type=activity)
    excused = bool(settings["excused_counts_as_attended"])
    summ = reports.summarize(df, excused)
    roster = students.students_frame(year.id, actor, branch_id=branch, class_id=cls, status="active",
                                     include_unenrolled=False)
    theme.kpi_row([
        ("Thiếu nhi đang sinh hoạt", f"{len(roster):,}", "#1B2A4A", f"{summ['sessions']} phiên trong kỳ"),
        ("Có mặt", f"{summ[C.PRESENT]:,}", C.STATUS_COLORS[C.PRESENT]),
        ("Đi trễ", f"{summ[C.LATE]:,}", C.STATUS_COLORS[C.LATE]),
        ("Tỷ lệ chuyên cần", theme.pct(summ["rate"]), settings["accent_color"],
         "(Có mặt + Trễ) / Đã có kết quả" + (" · tính cả có phép" if excused else "")),
        ("Vắng có phép", f"{summ[C.EXCUSED]:,}", C.STATUS_COLORS[C.EXCUSED]),
        ("Vắng không phép", f"{summ[C.ABSENT]:,}", C.STATUS_COLORS[C.ABSENT]),
        ("Chưa điểm danh", f"{summ[C.UNMARKED]:,}", C.STATUS_COLORS[C.UNMARKED], "không tính vào tỷ lệ"),
        ("Lượt điểm danh", f"{summ['marked']:,}", "#1B2A4A"),
    ])
    if df.empty:
        st.info("Chưa có dữ liệu điểm danh trong khoảng thời gian đã chọn.")
        return
    left, right = st.columns([1.5, 1])
    with left:
        st.subheader("Chuyên cần theo thời gian")
        period = st.segmented_control("Gom theo", ["day", "week", "month"], default="week", key="dash_period",
                                      format_func={"day": "Ngày", "week": "Tuần", "month": "Tháng"}.get) or "week"
        trend = reports.group_stats(reports.add_period(df, period, year), "period", excused)
        st.plotly_chart(charts.rate_trend(trend, "period"), config=CHART_CONFIG)
    with right:
        st.subheader("Phân bố trạng thái")
        st.plotly_chart(charts.status_donut(summ), config=CHART_CONFIG)
    l2, r2 = st.columns([1.5, 1])
    with l2:
        st.subheader("Tình trạng điểm danh từng lớp")
        by_class = reports.group_stats(df, "class_name", excused)
        st.plotly_chart(charts.status_by_group(by_class, "class_name"), config=CHART_CONFIG)
    with r2:
        st.subheader("Theo loại sinh hoạt")
        by_type = reports.group_stats(df, "activity_type", excused)
        st.plotly_chart(charts.rate_bars(by_type, "activity_type"), config=CHART_CONFIG)
    threshold = float(settings["low_attendance_threshold"])
    low = reports.low_attendance(df, threshold, excused_attended=excused)
    st.subheader(f"⚠️ Cần quan tâm: chuyên cần dưới {threshold:.0f}%")
    if low.empty:
        st.success("Không có em nào dưới ngưỡng trong kỳ đã chọn (tối thiểu 3 phiên đã có kết quả).")
    else:
        st.dataframe(reports.pretty(low[["code", "saint_name", "full_name", "class_name", "marked", C.PRESENT, C.LATE,
                                         C.EXCUSED, C.ABSENT, "rate"]]), hide_index=True,
                     column_config={"Chuyên cần (%)": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                                                      format="%.0f%%")})


def _today_panel(actor, year) -> None:
    today = attendance.now_local().date()

    @st.fragment(run_every=timedelta(seconds=15))
    def panel():
        df = sessions.list_sessions(year.id, actor, date_from=today, date_to=today)
        if df.empty:
            st.html("<div class='tn-card tn-muted'>Hôm nay chưa có buổi điểm danh nào. "
                    "Vào <b>Buổi sinh hoạt</b> hoặc <b>Điểm danh</b> để tạo nhanh.</div>")
            return
        st.subheader("Buổi hôm nay")
        scope = org.allowed_class_ids(actor, year.id)
        cols = st.columns(min(3, len(df)))
        for i, r in enumerate(df.itertuples()):
            counts = attendance.session_counts(int(r.id), scope)
            done = counts["total"] - counts[C.UNMARKED]
            with cols[i % len(cols)].container(border=True):
                st.markdown(f"**{r.title}** · {C.SESSION_STATUS_LABELS[r.status]}")
                st.caption(f"{r.start_time.strftime('%H:%M') if r.start_time else ''} · {r.classes}")
                st.progress(done / (counts["total"] or 1), text=f"{done}/{counts['total']} em đã điểm danh")
                st.caption(f"✅ {counts[C.PRESENT]} · ⏰ {counts[C.LATE]} · 📝 {counts[C.EXCUSED]} · ❌ {counts[C.ABSENT]}")
                if r.status == C.SESSION_OPEN and actor.can("attendance.mark"):
                    if st.button("Điểm danh", key=f"go_{r.id}", width="stretch"):
                        st.session_state["active_session_id"] = int(r.id)
                        go_to("diem-danh")
        st.caption(f"Tự cập nhật mỗi 15 giây · {attendance.now_local():%H:%M:%S}")

    panel()
