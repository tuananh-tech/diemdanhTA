"""Nhật ký hoạt động và nhật ký thay đổi điểm danh."""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from ... import config
from ... import constants as C
from ...services import attendance, audit, reports, sessions
from .. import state

ACTION_LABELS = {
    "auth.": "Đăng nhập / đăng xuất", "user.": "Tài khoản", "student.": "Thiếu nhi", "session.": "Buổi sinh hoạt",
    "qr.": "Thẻ QR", "settings.": "Cấu hình", "backup.": "Sao lưu", "report.": "Xuất báo cáo",
    "class.": "Lớp", "branch.": "Ngành", "year.": "Năm học", "face.": "Khuôn mặt",
}


def render() -> None:
    actor = state.actor()
    st.title("Nhật ký hoạt động")
    t1, t2 = st.tabs(["🧾 Hoạt động hệ thống", "✅ Thay đổi điểm danh"], key="tabs_audit")
    with t1:
        today = attendance.now_local().date()
        c1, c2, c3 = st.columns([1.5, 1, 1])
        rng = c1.date_input("Khoảng ngày", (today - timedelta(days=7), today), format="DD/MM/YYYY", key="audit_rng")
        prefix = c2.selectbox("Loại", [None, *ACTION_LABELS], format_func=lambda p: "Tất cả" if p is None else ACTION_LABELS[p])
        user = c3.text_input("Tên đăng nhập")
        if not isinstance(rng, (tuple, list)) or len(rng) != 2:
            return

        def utc(d, end=False):
            local = datetime.combine(d + timedelta(days=1) if end else d, time(0), tzinfo=config.LOCAL_TZ)
            return local.astimezone(timezone.utc).replace(tzinfo=None)

        df = audit.list_audit(utc(rng[0]), utc(rng[1], True), prefix, user.strip().lower() or None, limit=2000)
        if df.empty:
            st.info("Không có hoạt động.")
            return
        view = pd.DataFrame({
            "Thời gian": df["at"].map(lambda d: attendance.to_local(d).strftime("%d/%m/%Y %H:%M:%S")),
            "Người dùng": df.username.fillna("—"), "Hành động": df.action, "Đối tượng": df.entity.fillna(""),
            "ID": df.entity_id.fillna(""), "Chi tiết": df.details.fillna("").map(_short),
        })
        st.dataframe(view, hide_index=True, height=560)
        st.download_button("⬇️ Xuất CSV", reports.to_csv(view), "nhat_ky.csv", mime="text/csv")
    with t2:
        year = state.year()
        df = sessions.list_sessions(year.id, actor)
        if df.empty:
            st.info("Chưa có buổi nào.")
            return
        labels = {int(r.id): f"{r.session_date:%d/%m/%Y} · {r.title}" for r in df.itertuples()}
        sid = st.selectbox("Buổi", list(labels), format_func=labels.get)
        log = attendance.recent_activity(sid, limit=1000)
        if log.empty:
            st.info("Chưa có thay đổi.")
            return
        st.dataframe(pd.DataFrame({
            "Thời gian": log["at"].map(lambda d: attendance.to_local(d).strftime("%d/%m %H:%M:%S")),
            "Mã": log.code, "Họ tên": (log.saint_name.fillna("") + " " + log.full_name).str.strip(),
            "Từ": log.old_status.map(lambda s: C.STATUS_LABELS.get(s, "—")),
            "Sang": log.new_status.map(C.STATUS_LABELS), "Cách": log.method.map(lambda m: C.METHOD_LABELS.get(m, m)),
            "Người thực hiện": log.by.fillna("Hệ thống"),
        }), hide_index=True, height=560)


def _short(text: str) -> str:
    if not text:
        return ""
    try:
        data = json.loads(text)
        return ", ".join(f"{k}={v}" for k, v in data.items())[:200]
    except ValueError:
        return text[:200]
