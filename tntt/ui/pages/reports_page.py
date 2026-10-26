"""Báo cáo: thống kê theo thời gian / ngành / lớp / cá nhân / loại sinh hoạt, sổ điểm danh, xuất file."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from ... import constants as C
from ...services import attendance, audit, branding, org, reports, sessions
from .. import charts, state, theme

GROUPS = {
    "period": "Thời gian", "branch": "Ngành", "class_name": "Lớp", "student": "Cá nhân",
    "activity_type": "Loại sinh hoạt", "matrix": "Sổ điểm danh (em × buổi)", "session": "Một buổi cụ thể",
}
PERIODS = {"day": "Ngày", "week": "Tuần", "month": "Tháng", "semester": "Học kỳ", "year": "Năm học"}


def render() -> None:
    actor = state.actor()
    year = state.year()
    settings = branding.get_settings()
    excused = bool(settings["excused_counts_as_attended"])
    st.title("Báo cáo")
    today = attendance.now_local().date()
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.6, 1, 1, 1])
        end = min(today, year.end_date) if today >= year.start_date else year.end_date
        rng = c1.date_input("Khoảng thời gian", (year.start_date, end), min_value=year.start_date,
                            max_value=year.end_date, format="DD/MM/YYYY")
        branches = {b.id: b.name for b in org.list_branches()}
        branch = c2.selectbox("Ngành", [None, *branches], format_func=lambda b: "Tất cả" if b is None else branches[b])
        copts = org.class_options(year.id, actor)
        cls = c3.selectbox("Lớp", [None, *copts], format_func=lambda c: "Tất cả" if c is None else copts[c])
        activity = c4.selectbox("Loại sinh hoạt", [None, *C.ACTIVITY_TYPES], format_func=lambda a: a or "Tất cả")
        g1, g2 = st.columns([2, 1])
        group = g1.segmented_control("Thống kê theo", list(GROUPS), format_func=GROUPS.get, default="class_name",
                                     required=True) or "class_name"
        period = g2.selectbox("Gom theo", list(PERIODS), format_func=PERIODS.get, index=2,
                              disabled=group != "period")
    if not isinstance(rng, (tuple, list)) or len(rng) != 2:
        st.info("Chọn đủ ngày bắt đầu và kết thúc.")
        return

    if group == "session":
        _session_report(actor, year, settings)
        return
    df = reports.attendance_frame(year.id, actor, date_from=rng[0], date_to=rng[1], branch_id=branch, class_id=cls,
                                  activity_type=activity)
    summ = reports.summarize(df, excused)
    theme.kpi_row([
        ("Số buổi", summ["sessions"], "#1B2A4A"), ("Số em", summ["students"], "#1B2A4A"),
        ("Đã có kết quả", summ["marked"], "#1B2A4A"),
        ("Chuyên cần", theme.pct(summ["rate"]), settings["accent_color"]),
    ])
    st.caption("Chuyên cần = (Có mặt + Đi trễ) ÷ số lượt đã có kết quả (không tính 'Chưa điểm danh'), chỉ trên các buổi "
               "em thuộc đối tượng tham dự." + (" Vắng có phép được tính như có mặt (theo cấu hình)." if excused else ""))
    if df.empty:
        st.info("Không có dữ liệu.")
        return

    if group == "matrix":
        table = reports.attendance_matrix(df).rename(columns={"class_name": "Lớp", "code": "Mã", "saint_name": "Tên Thánh",
                                                              "full_name": "Họ và tên"})
        st.caption("✓ có mặt · T đi trễ · P vắng có phép · K vắng không phép · · chưa điểm danh")
        chart = None
    elif group == "student":
        table = reports.pretty(reports.student_stats(df, excused))
        chart = None
    else:
        key = group
        data = reports.add_period(df, period, year) if group == "period" else df
        stats = reports.group_stats(data, key, excused)
        chart = charts.rate_trend(stats, key) if group == "period" else charts.status_by_group(stats, key)
        table = reports.pretty(stats.rename(columns={key: GROUPS[group] if group != "period" else "Thời gian"}))
    if chart is not None:
        st.plotly_chart(chart, config={"displaylogo": False})
    st.dataframe(table, hide_index=True, height=min(620, 38 + 35 * len(table)))

    filters = _filter_text(rng, branches.get(branch), copts.get(cls), activity, group, period)
    title = f"Báo cáo điểm danh – {GROUPS[group]}"
    _exports(actor, settings, title, filters, table, summ if group != "matrix" else None)


def _filter_text(rng, branch, cls, activity, group, period) -> str:
    parts = [f"Từ {rng[0]:%d/%m/%Y} đến {rng[1]:%d/%m/%Y}"]
    if branch:
        parts.append(f"Ngành: {branch}")
    if cls:
        parts.append(f"Lớp: {cls}")
    if activity:
        parts.append(f"Loại: {activity}")
    if group == "period":
        parts.append(f"Gom theo: {PERIODS[period]}")
    return " · ".join(parts)


def _org_lines(settings) -> list[str]:
    lines = [settings["xudoan_name"], " · ".join(x for x in (settings["parish_name"], settings.get("diocese")) if x)]
    if settings.get("motto"):
        lines.append(settings["motto"])
    return lines


def _exports(actor, settings, title, filters, table: pd.DataFrame, summ) -> None:
    st.markdown("**Xuất báo cáo**")
    c1, c2, c3 = st.columns(3)
    base = "bao_cao_diem_danh"
    org_name = f"{settings['xudoan_name']} – {settings['parish_name']}"
    if c1.download_button("⬇️ Excel", reports.to_excel({"Báo cáo": table}, title=title, subtitle=filters,
                                                        org_name=org_name), f"{base}.xlsx"):
        audit.log(actor, "report.export", "report", None, format="xlsx", title=title)
    if c2.download_button("⬇️ CSV", reports.to_csv(table), f"{base}.csv", mime="text/csv"):
        audit.log(actor, "report.export", "report", None, format="csv", title=title)
    if c3.button("📄 Tạo PDF"):
        with st.spinner("Đang tạo PDF…"):
            pdf = reports.to_pdf(title=title, subtitle=filters, org_lines=_org_lines(settings),
                                 logo_png=branding.logo_png(max_px=200), summary=summ, tables=[("Chi tiết", table)])
        st.session_state["report_pdf"] = pdf
    if st.session_state.get("report_pdf"):
        if c3.download_button("⬇️ Tải PDF", st.session_state["report_pdf"], f"{base}.pdf", mime="application/pdf"):
            audit.log(actor, "report.export", "report", None, format="pdf", title=title)


def _session_report(actor, year, settings) -> None:
    today = attendance.now_local().date()
    df = sessions.list_sessions(year.id, actor, date_from=today - timedelta(days=366), date_to=today + timedelta(days=30))
    df = df[df.status != C.SESSION_SCHEDULED]
    if df.empty:
        st.info("Chưa có buổi nào đã mở.")
        return
    labels = {int(r.id): f"{r.session_date:%d/%m/%Y} · {r.title} · {r.classes}" for r in df.itertuples()}
    sid = st.selectbox("Chọn buổi", list(labels), format_func=labels.get)
    sess = sessions.get_session(sid)
    scope = sessions.actor_classes_in_session(actor, sess)
    roster = attendance.roster_frame(sid, class_ids=scope)
    counts = attendance.session_counts(sid, scope)
    table = pd.DataFrame({
        "Lớp": roster.class_name, "Mã": roster.code, "Tên Thánh": roster.saint_name.fillna(""),
        "Họ và tên": roster.full_name, "Trạng thái": roster.status.map(C.STATUS_LABELS),
        "Giờ": roster.marked_at.map(lambda d: attendance.to_local(d).strftime("%H:%M") if pd.notna(d) and d else ""),
        "Cách ghi nhận": roster.method.map(lambda m: C.METHOD_LABELS.get(m, "") if m else ""),
        "Người ghi nhận": roster.marked_by.fillna(""), "Ghi chú": roster.note.fillna(""),
    })
    summ = {**counts, "rate": None}
    marked = sum(counts[s] for s in C.MARKED_STATUSES)
    if marked:
        summ["rate"] = (counts[C.PRESENT] + counts[C.LATE]) / marked * 100
    st.dataframe(table, hide_index=True, height=min(620, 38 + 35 * len(table)))
    title = f"Điểm danh: {sess.title}"
    filters = f"Ngày {sess.session_date:%d/%m/%Y} · {sess.activity_type} · {C.SESSION_STATUS_LABELS[sess.status]}"
    _exports(actor, settings, title, filters, table, summ)
