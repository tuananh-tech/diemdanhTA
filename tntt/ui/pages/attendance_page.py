"""Trang Điểm danh: 3 phương thức trong cùng một trang.

- Danh sách: chạm 1 lần để đổi trạng thái (lưu ngay, khóa lạc quan theo version).
- Quét QR: camera của trình duyệt, quét liên tục, phản hồi màu + âm thanh.
- Khuôn mặt: chỉ hiện khi module được bật hợp lệ; chỉ gợi ý, phải xác nhận.
"""
from __future__ import annotations

import html
import time as _time
from datetime import date, datetime, time, timedelta

import streamlit as st

from ... import constants as C
from ...components.qr_scanner import qr_scanner
from ...security import P_ATTEND_CLOSED, P_SESSIONS
from ...services import attendance, branding, org, sessions
from ...services import face as face_svc
from .. import state

MODES = {"list": "📋 Danh sách", "qr": "📷 Quét QR", "face": "🙂 Khuôn mặt"}
PAGE_SIZE = 40
STATUS_ICONS = {C.PRESENT: "✅", C.LATE: "⏰", C.EXCUSED: "📝", C.ABSENT: "❌"}


def render_manual() -> None:
    _render(default_mode="list")


def render_scan() -> None:
    _render(default_mode="qr")


# ---------------------------------------------------------------------------
def _fmt_time(dt) -> str:
    loc = attendance.to_local(dt)
    return loc.strftime("%H:%M") if loc else ""


def _session_label(r) -> str:
    dot = {"open": "🟢", "scheduled": "🕒", "closed": "🔒"}[r.status]
    t = r.start_time.strftime(" %H:%M") if r.start_time else ""
    return f"{dot} {r.title} · {r.session_date:%d/%m}{t} · {r.classes} ({r.marked}/{r.eligible})"


def _pick_session(actor, mode: str):
    year_id = state.year_id()
    today = attendance.now_local().date()
    df = sessions.list_sessions(year_id, actor, date_from=today - timedelta(days=45), date_to=today + timedelta(days=14))
    if mode == "qr":
        df = df[df["status"] == C.SESSION_OPEN]
    if df.empty:
        return None
    # ưu tiên phiên đang mở gần hôm nay nhất
    df = df.assign(_open=(df["status"] != C.SESSION_OPEN),
                   _dist=df["session_date"].map(lambda d: abs((d - today).days))).sort_values(["_open", "_dist"])
    ids = [int(i) for i in df["id"]]
    labels = {int(r.id): _session_label(r) for r in df.itertuples()}
    current = st.session_state.get("active_session_id")
    sid = st.selectbox("Buổi điểm danh", ids, index=ids.index(current) if current in ids else 0,
                       format_func=labels.get, key=f"pick_{mode}")
    st.session_state["active_session_id"] = sid
    return sessions.get_session(sid)


def _quick_create(actor) -> None:
    if not actor.can(P_SESSIONS):
        return
    with st.expander("➕ Tạo buổi điểm danh nhanh cho hôm nay", expanded=False):
        year_id = state.year_id()
        opts = org.class_options(year_id, actor)
        with st.form("quick_session", border=False):
            c1, c2 = st.columns(2)
            activity = c1.selectbox("Loại sinh hoạt", C.ACTIVITY_TYPES, index=1)
            start = c2.time_input("Giờ bắt đầu", value=time(8, 0), step=300)
            scope_all = st.toggle("Toàn Xứ đoàn", value=False, disabled=not actor.is_global)
            class_ids = st.multiselect("Lớp tham dự", list(opts), format_func=opts.get, disabled=False,
                                       placeholder="Chọn lớp…")
            late = st.number_input("Tính đi trễ sau (phút)", 0, 120, 15, step=5)
            ok = st.form_submit_button("Tạo và mở phiên", type="primary")
        if ok:
            with state.guard():
                late_after = (datetime.combine(date.today(), start) + timedelta(minutes=int(late))).time()
                sid = sessions.create_session(actor, year_id=year_id, title="", activity_type=activity,
                                              session_date=attendance.now_local().date(), start_time=start,
                                              late_after=late_after, class_ids=class_ids, scope_all=scope_all)
                st.session_state["active_session_id"] = sid
                state.flash("success", "Đã tạo và mở phiên điểm danh.")
                st.rerun()


def _render(default_mode: str) -> None:
    actor = state.actor()
    settings = branding.get_settings()
    face_on = face_svc.is_enabled(settings)
    modes = ["list", "qr"] + (["face"] if face_on else [])
    st.title("Điểm danh" if default_mode == "list" else "Quét QR điểm danh")
    mode = st.segmented_control("Phương thức", modes, format_func=MODES.get, default=default_mode,
                                key=f"mode_{default_mode}", label_visibility="collapsed", required=True) or default_mode
    sess = _pick_session(actor, mode)
    if sess is None:
        st.info("Chưa có buổi điểm danh phù hợp" + (" đang mở." if mode == "qr" else ".")
                + " Tạo buổi mới bên dưới hoặc tại trang **Buổi sinh hoạt**.")
        _quick_create(actor)
        return
    if not sessions.can_view_session(actor, sess):
        st.error("Bạn không được phân công cho buổi này.")
        return
    if sess.status == C.SESSION_SCHEDULED:
        st.warning("Buổi này mới **lên lịch**, chưa mở. Mở phiên để lập danh sách tham dự.")
        if actor.can(P_SESSIONS) and st.button("Mở phiên ngay", type="primary"):
            with state.guard():
                res = sessions.open_session(actor, sess.id)
                state.flash("success", f"Đã mở phiên – danh sách {res['added']} em.")
                st.rerun()
        return
    if sess.status == C.SESSION_CLOSED:
        st.info("🔒 Phiên đã đóng." + (" Bạn có quyền chỉnh sửa." if actor.can(P_ATTEND_CLOSED) else " Chỉ xem."))

    if mode == "list":
        _manual(actor, sess)
    elif mode == "qr":
        _scanner(actor, sess, settings)
    else:
        _face(actor, sess, settings)
    _quick_create(actor)


# ---------------------------------------------------------------------------
# Danh sách (thủ công)
# ---------------------------------------------------------------------------
def _counts_bar(counts: dict) -> None:
    total = counts["total"] or 1
    done = total - counts[C.UNMARKED]
    st.progress(done / total, text=f"Đã điểm danh {done}/{counts['total']} em")
    # Dải chip gọn: trên điện thoại vẫn nằm trong 1–2 dòng, không đẩy danh sách xuống xa.
    chips = "".join(
        f"<span class='tn-chip' style='--c:{C.STATUS_COLORS[s]}'><b>{counts[s]}</b> {C.STATUS_LABELS[s]}</span>"
        for s in (C.PRESENT, C.LATE, C.EXCUSED, C.ABSENT, C.UNMARKED))
    st.html(f"<div class='tn-chips'>{chips}</div>")


def _on_status_change(actor, record_id: int, key: str) -> None:
    value = st.session_state.get(key)
    new_status = value or C.UNMARKED
    seen = st.session_state.setdefault("seen_versions", {})
    res = attendance.set_status(actor, record_id, new_status, expected_version=seen.get(record_id))
    if res.ok:
        if res.version is not None:
            seen[record_id] = res.version
        if res.kind == "success":
            name = res.student.get("full_name", "")
            st.toast(f"{STATUS_ICONS.get(new_status, '↩️')} {name}: {C.STATUS_LABELS[new_status]}")
    else:
        # trả widget về trạng thái thật trong DB
        st.session_state[key] = res.status if res.status in C.MARKED_STATUSES else None
        if res.version is not None:
            seen[record_id] = res.version
        else:
            seen.pop(record_id, None)
        st.toast(("⚠️ " if res.kind == "conflict" else "⛔ ") + res.message)


def _save_note(actor, record_id: int, key: str) -> None:
    seen = st.session_state.setdefault("seen_versions", {})
    rec_status = st.session_state.get(f"att_{record_id}") or C.UNMARKED
    res = attendance.set_status(actor, record_id, rec_status, note=st.session_state.get(key, ""),
                                expected_version=seen.get(record_id))
    if res.ok and res.version:
        seen[record_id] = res.version
    st.toast("📝 Đã lưu ghi chú" if res.ok else "⚠️ " + res.message)


def _manual(actor, sess) -> None:
    scope = sessions.actor_classes_in_session(actor, sess)
    writable = sess.status == C.SESSION_OPEN or actor.can(P_ATTEND_CLOSED)
    session_classes = sessions.session_class_ids(sess.id)
    opts = org.class_options(sess.school_year_id)
    class_choices = [c for c in opts if (sess.scope_all or c in session_classes) and (scope is None or c in scope)]

    c1, c2, c3 = st.columns([2, 1.4, 1])
    search = c1.text_input("Tìm tên hoặc mã", placeholder="Gõ không dấu cũng được…", key=f"q_{sess.id}")
    cls = c2.selectbox("Lớp", [None] + class_choices, format_func=lambda c: "Tất cả lớp" if c is None else opts[c],
                       key=f"cls_{sess.id}")
    only_unmarked = c3.toggle("Chỉ em chưa điểm danh", key=f"un_{sess.id}")
    auto = st.toggle("Tự làm mới mỗi 20 giây (xem thay đổi của Huynh trưởng khác)", value=True, key=f"auto_{sess.id}")

    @st.fragment(run_every=timedelta(seconds=20) if auto else None)
    def body():
        class_filter = {cls} if cls else scope
        counts = attendance.session_counts(sess.id, scope)
        _counts_bar(counts)
        df = attendance.roster_frame(sess.id, class_ids=class_filter, search=search, only_unmarked=only_unmarked)
        if df.empty:
            st.info("Không có em nào khớp bộ lọc." if (search or only_unmarked or cls) else "Danh sách phiên trống.")
            return
        if writable:
            _bulk_tools(actor, sess, df)
        pages = max(1, (len(df) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = 1
        if pages > 1:
            page = st.number_input(f"Trang (1–{pages})", 1, pages, 1, key=f"page_{sess.id}")
        seen = st.session_state.setdefault("seen_versions", {})
        for r in df.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE].itertuples():
            rid = int(r.record_id)
            key = f"att_{rid}"
            if seen.get(rid) != int(r.version) or key not in st.session_state:
                st.session_state[key] = r.status if r.status in C.MARKED_STATUSES else None
                seen[rid] = int(r.version)
            _row(actor, r, rid, key, writable)

    body()


def _row(actor, r, rid: int, key: str, writable: bool) -> None:
    with st.container(border=True, key=f"tnrow_{rid}"):
        left, right = st.columns([1.15, 1.85], vertical_alignment="center")
        name = html.escape(f"{r.saint_name or ''} {r.full_name}".strip())
        meta = [html.escape(r.code), html.escape(r.class_name or "")]
        if r.status != C.UNMARKED:
            meta.append(f"{C.METHOD_LABELS.get(r.method, '')} {_fmt_time(r.marked_at)} · {html.escape(r.marked_by or '')}")
        note = f"<div class='tn-row-meta'>📝 {html.escape(r.note)}</div>" if r.note else ""
        # Tên + nút ghi chú cùng 1 hàng; hàng nút trạng thái được trọn chiều ngang (quan trọng trên điện thoại).
        info, more = left.columns([6, 1], vertical_alignment="center", wrap=False)
        info.html(f"<div class='tn-row-name'>{name}</div><div class='tn-row-meta'>{' · '.join(m for m in meta if m)}</div>{note}")
        right.segmented_control(
            "Trạng thái", C.MARKED_STATUSES, key=key, label_visibility="collapsed",
            format_func=lambda s: f"{STATUS_ICONS[s]} {C.STATUS_SHORT[s]}", disabled=not writable,
            on_change=_on_status_change, args=(actor, rid, key), width="stretch")
        with more.popover("📝", help="Ghi chú / lịch sử", type="tertiary"):
            nk = f"note_{rid}"
            st.text_input("Ghi chú", value=r.note or "", key=nk, max_chars=255, disabled=not writable)
            st.button("Lưu ghi chú", key=f"savenote_{rid}", on_click=_save_note, args=(actor, rid, nk),
                      disabled=not writable)
            hist = attendance.record_history(rid)
            if not hist.empty:
                st.caption("Lịch sử thay đổi")
                for h in hist.head(6).itertuples():
                    st.caption(f"{_fmt_time(h.at)} · {C.STATUS_LABELS.get(h.old_status, '—')} → "
                               f"{C.STATUS_LABELS[h.new_status]} · {h.by or 'Hệ thống'}")


def _bulk_tools(actor, sess, df) -> None:
    unmarked = df[df["status"] == C.UNMARKED]
    with st.expander(f"⚡ Thao tác nhanh nhiều em ({len(unmarked)} em chưa điểm danh trong danh sách đang lọc)"):
        c1, c2 = st.columns([1, 1])
        confirm = c1.checkbox("Xác nhận đánh dấu tất cả em CHƯA điểm danh (đang lọc) là Có mặt", key=f"cf_{sess.id}")
        if c2.button("✅ Tất cả có mặt", disabled=not confirm or unmarked.empty, type="primary", key=f"all_{sess.id}"):
            res = attendance.bulk_set(actor, sess.id, [int(x) for x in unmarked["record_id"]], C.PRESENT)
            (st.success if res.ok else st.error)(res.message)
            st.session_state.pop("seen_versions", None)
            st.rerun(scope="fragment")
        st.divider()
        labels = {int(r.record_id): f"{r.full_name} ({r.code})" for r in df.itertuples()}
        chosen = st.multiselect("Chọn nhiều em", list(labels), format_func=labels.get, key=f"multi_{sess.id}")
        status = st.radio("Đặt trạng thái", C.MARKED_STATUSES, format_func=C.STATUS_LABELS.get, horizontal=True,
                          key=f"multist_{sess.id}")
        overwrite = st.checkbox("Ghi đè cả những em đã có trạng thái", key=f"ow_{sess.id}")
        if st.button("Áp dụng cho các em đã chọn", disabled=not chosen, key=f"apply_{sess.id}"):
            res = attendance.bulk_set(actor, sess.id, chosen, status, only_unmarked=not overwrite)
            (st.success if res.ok else st.error)(res.message)
            st.session_state.pop("seen_versions", None)
            st.rerun(scope="fragment")


# ---------------------------------------------------------------------------
# Quét QR
# ---------------------------------------------------------------------------
def _result_payload(res: attendance.MarkResult, nonce: str) -> dict:
    stu = res.student or {}
    name = f"{stu.get('saint_name', '')} {stu.get('full_name', '')}".strip()
    if res.kind == "success":
        title, sub = f"✓ {name}", f"{C.STATUS_LABELS[res.status]} · {stu.get('class_name', '')}"
    elif res.kind == "duplicate":
        title = f"Đã điểm danh: {name}"
        sub = f"{C.STATUS_LABELS.get(res.status, '')} lúc {_fmt_time(res.marked_at)}" + (f" · {res.marked_by}" if res.marked_by else "")
    else:
        title, sub = res.message, name
    return {"nonce": nonce, "kind": res.kind, "title": title, "subtitle": sub}


def _handle_code(actor, sess, text: str, method: str, nonce: str, settings: dict) -> None:
    res = attendance.check_in(actor, sess.id, text, method=method,
                              accept_plain_code=bool(settings.get("accept_plain_code_qr")))
    payload = _result_payload(res, nonce)
    st.session_state[f"scanres_{sess.id}"] = payload
    history = st.session_state.setdefault(f"scanlog_{sess.id}", [])
    history.insert(0, {**payload, "at": attendance.now_local().strftime("%H:%M:%S")})
    del history[15:]


def _scanner(actor, sess, settings) -> None:
    if sess.status != C.SESSION_OPEN:
        st.warning("Chỉ quét QR khi phiên đang mở.")
        return
    key = f"scanner_{sess.id}"

    @st.fragment
    def scan_area():
        value = st.session_state.get(key)
        if isinstance(value, dict) and value.get("nonce") and value["nonce"] != st.session_state.get(f"lastnonce_{sess.id}"):
            st.session_state[f"lastnonce_{sess.id}"] = value["nonce"]
            _handle_code(actor, sess, str(value.get("text", ""))[:200], C.METHOD_QR, value["nonce"], settings)
        left, right = st.columns([1.15, 1], gap="large")
        with left:
            qr_scanner(result=st.session_state.get(f"scanres_{sess.id}"), key=key)
            with st.form(f"code_{sess.id}", clear_on_submit=True, border=True):
                st.caption("Camera không dùng được? Nhập mã thiếu nhi (hoặc dùng máy quét mã cầm tay):")
                cc1, cc2 = st.columns([3, 1], vertical_alignment="bottom")
                code = cc1.text_input("Mã thiếu nhi", label_visibility="collapsed", placeholder="Ví dụ: 0012")
                if cc2.form_submit_button("Điểm danh", type="primary", width="stretch") and code.strip():
                    _handle_code(actor, sess, code.strip(), C.METHOD_CODE, f"m{_time.time_ns()}", settings)
                    st.rerun(scope="fragment")
        with right:
            last = st.session_state.get(f"scanres_{sess.id}")
            if last:
                color = {"success": C.STATUS_COLORS[C.PRESENT], "duplicate": "#D48A00"}.get(last["kind"], C.STATUS_COLORS[C.ABSENT])
                st.html(f"<div class='tn-result' style='background:{color}'><div class='n'>{html.escape(last['title'])}</div>"
                        f"<div class='m'>{html.escape(last['subtitle'] or '')}</div></div>")
            else:
                st.html("<div class='tn-card tn-muted'>Kết quả quét sẽ hiện ở đây.</div>")
            live_counts()
            log = st.session_state.get(f"scanlog_{sess.id}", [])
            if log:
                st.caption("Lượt quét gần đây trên thiết bị này")
                icon = {"success": "🟢", "duplicate": "🟡"}
                for item in log[:8]:
                    st.markdown(f"{icon.get(item['kind'], '🔴')} `{item['at']}` {html.escape(item['title'])}")

    @st.fragment(run_every=timedelta(seconds=6))
    def live_counts():
        counts = attendance.session_counts(sess.id)
        done = counts["total"] - counts[C.UNMARKED]
        st.progress(done / (counts["total"] or 1), text=f"Đã điểm danh {done}/{counts['total']} em "
                    f"(có mặt {counts[C.PRESENT]}, trễ {counts[C.LATE]})")

    scan_area()
    st.caption("Mẹo: trên điện thoại hệ thống ưu tiên camera sau. Có thể đổi camera trong danh sách khi máy có nhiều camera. "
               "Website phải mở qua HTTPS để trình duyệt cho phép dùng camera.")


# ---------------------------------------------------------------------------
# Khuôn mặt (tùy chọn)
# ---------------------------------------------------------------------------
def _face(actor, sess, settings) -> None:
    ok, reason = face_svc.engine_status()
    if not ok:
        st.warning(f"Module khuôn mặt đã bật nhưng chưa sẵn sàng: {reason}. Hãy dùng QR hoặc danh sách.")
        return
    if sess.status != C.SESSION_OPEN:
        st.warning("Chỉ dùng khi phiên đang mở.")
        return
    st.info("Hệ thống chỉ **gợi ý**. Huynh trưởng phải nhìn và xác nhận đúng em rồi mới bấm ghi nhận. "
            "Ảnh chụp không được lưu.")
    photo = st.camera_input("Chụp ảnh (1 hoặc vài em)", key=f"face_cam_{sess.id}")
    if not photo:
        return
    try:
        suggestions = face_svc.suggest(sess.id, photo.getvalue(), float(settings["face_threshold"]),
                                       float(settings["face_margin"]))
    except Exception as exc:  # noqa: BLE001 - lỗi module không ảnh hưởng phần còn lại
        st.error(f"Không xử lý được ảnh: {exc}")
        return
    if not suggestions:
        st.warning("Không phát hiện khuôn mặt nào.")
    for i, sug in enumerate(suggestions):
        with st.container(border=True):
            if sug["decision"] == "suggest":
                st.markdown(f"**Gợi ý:** {html.escape(sug['name'])} (`{sug['code']}`) · độ tương đồng {sug['score']:.2f}")
                if st.button("Đúng em này – ghi nhận", key=f"face_ok_{sess.id}_{i}_{sug['student_id']}", type="primary"):
                    res = attendance.check_in(actor, sess.id, student_id=sug["student_id"], method=C.METHOD_FACE)
                    (st.success if res.ok else st.warning)(
                        f"{sug['name']}: {C.STATUS_LABELS.get(res.status, '') if res.ok else res.message}")
            else:
                st.markdown("**Không chắc chắn** – không đưa ra gợi ý. Hãy dùng QR hoặc điểm danh thủ công.")
