"""Cấu hình Xứ đoàn: thông tin, màu, logo, QR mặc định, quy tắc, sao lưu, module khuôn mặt."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from ... import config, qrimage
from ...security import P_BACKUP
from ...services import backup, branding, qrcodes, students
from ...services import face as face_svc
from .. import state


def render() -> None:
    actor = state.actor()
    s = branding.get_settings(fresh=True)
    st.title("Cấu hình Xứ đoàn")
    tabs = st.tabs(["⛪ Thông tin", "🖼️ Logo", "🔳 QR mặc định", "⚙️ Quy tắc điểm danh", "💾 Sao lưu", "🙂 Khuôn mặt"], key="tabs_settings")
    with tabs[0]:
        _info(actor, s)
    with tabs[1]:
        _logos(actor, s)
    with tabs[2]:
        _qr_defaults(actor, s)
    with tabs[3]:
        _rules(actor, s)
    with tabs[4]:
        _backup(actor)
    with tabs[5]:
        _face(actor, s)


def _info(actor, s) -> None:
    with st.form("info"):
        c1, c2 = st.columns(2)
        xudoan = c1.text_input("Tên Xứ đoàn *", s["xudoan_name"], max_chars=120)
        parish = c2.text_input("Tên Giáo xứ *", s["parish_name"], max_chars=120)
        diocese = c1.text_input("Giáo phận (tùy chọn)", s.get("diocese", ""), max_chars=120)
        motto = c2.text_input("Khẩu hiệu (tùy chọn)", s.get("motto", ""), max_chars=160)
        c3, c4, c5 = st.columns(3)
        primary = c3.color_picker("Màu nhận diện chính", s["primary_color"])
        accent = c4.color_picker("Màu nhấn", s["accent_color"])
        size = c5.slider("Kích thước logo trên header (px)", 40, 110, int(s["logo_display_px"]), 2)
        st.caption("Năm học hiện tại được chọn ở trang **Ngành / Lớp → Năm học**.")
        if st.form_submit_button("Lưu thông tin", type="primary"):
            if not xudoan.strip() or not parish.strip():
                st.error("Cần nhập tên Xứ đoàn và Giáo xứ.")
                return
            with state.guard():
                branding.save_settings(actor, {"xudoan_name": xudoan.strip(), "parish_name": parish.strip(),
                                               "diocese": diocese.strip(), "motto": motto.strip(),
                                               "primary_color": primary, "accent_color": accent,
                                               "logo_display_px": size})
                st.cache_data.clear()
                state.flash("success", "Đã lưu thông tin Xứ đoàn.")
                st.rerun()


def _logos(actor, s) -> None:
    kind = st.radio("Logo cần chỉnh", list(branding.LOGO_KEYS), format_func=branding.LOGO_KEYS.get, horizontal=True)
    current, editor = st.columns([1, 2], gap="large")
    with current:
        st.markdown("**Đang dùng**")
        st.image(branding.logo_png(kind, 300), width=180)
        st.caption("Logo tải lên" if branding.has_custom_logo(kind) else "Logo mặc định của hệ thống")
        if branding.has_custom_logo(kind) and st.button("↩️ Khôi phục logo mặc định", key=f"reset_{kind}"):
            with state.guard():
                branding.reset_logo(actor, kind)
                st.cache_data.clear()
                state.flash("success", "Đã khôi phục logo mặc định.")
                st.rerun()
        st.caption("Logo Xứ đoàn xuất hiện ở header, sidebar, trang đăng nhập, thẻ thiếu nhi, báo cáo in và giữa QR. "
                   "Logo lưu trong cơ sở dữ liệu nên không mất khi khởi động lại.")
    with editor:
        up = st.file_uploader("Tải logo mới (PNG, JPG, WebP · tối đa 5 MB)", type=["png", "jpg", "jpeg", "webp"],
                              key=f"up_{kind}")
        if not up:
            st.info("Nên dùng ảnh PNG nền trong suốt, hình vuông, tối thiểu 500×500 px.")
            return
        try:
            img = branding.load_upload(up.getvalue())
        except ValueError as exc:
            st.error(str(exc))
            return
        c1, c2 = st.columns(2)
        crop_l = c1.slider("Cắt trái", 0.0, 0.45, 0.0, 0.01)
        crop_r = c1.slider("Cắt phải", 0.0, 0.45, 0.0, 0.01)
        crop_t = c2.slider("Cắt trên", 0.0, 0.45, 0.0, 0.01)
        crop_b = c2.slider("Cắt dưới", 0.0, 0.45, 0.0, 0.01)
        c3, c4, c5 = st.columns(3)
        rotate = c3.select_slider("Xoay", [0, 90, 180, 270], 0)
        square = c4.checkbox("Căn giữa thành hình vuông", True)
        remove_white = c5.checkbox("Xóa nền trắng", False, help="Biến các điểm gần trắng thành trong suốt")
        padding = st.slider("Lề quanh logo", 0.0, 0.2, 0.04, 0.01, disabled=not square)
        try:
            edited = branding.process_logo(img, branding.LogoEdit(crop_l, crop_t, crop_r, crop_b, square, padding,
                                                                  remove_white, rotate))
        except ValueError as exc:
            st.error(str(exc))
            return
        p1, p2, p3 = st.columns(3)
        p1.image(edited, caption="Xem trước", width=160)
        hdr = edited.copy()
        hdr.thumbnail((96, 96))
        p2.image(hdr, caption="Trên header", width=64)
        res = qrimage.make_qr(qrcodes.payload_for("PREVIEW23456"), logo=edited, logo_ratio=float(s["qr_logo_ratio"]),
                              fg=s["primary_color"] if s["qr_color_mode"] == "brand" else "#000000")
        p3.image(res.image, caption="Trong QR", width=160)
        (st.success if res.verified and res.logo_applied else st.warning)(res.message)
        if st.button("💾 Lưu logo này", type="primary", key=f"save_{kind}"):
            with state.guard():
                branding.save_logo(actor, kind, edited)
                st.cache_data.clear()
                state.flash("success", "Đã lưu logo. Thẻ và QR tạo từ bây giờ sẽ dùng logo mới.")
                st.rerun()


def _qr_defaults(actor, s) -> None:
    with st.form("qr_defaults"):
        use_logo = st.toggle("Mặc định chèn logo giữa QR", bool(s["qr_use_logo"]))
        source = st.radio("Logo trong QR", list(branding.LOGO_KEYS), format_func=branding.LOGO_KEYS.get,
                          index=list(branding.LOGO_KEYS).index(s["qr_logo_source"]), horizontal=True)
        mode = st.radio("Màu QR mặc định", ["bw", "brand"], format_func={"bw": "Trắng đen", "brand": "Màu nhận diện"}.get,
                        index=0 if s["qr_color_mode"] == "bw" else 1, horizontal=True)
        ratio = st.slider("Kích thước logo (tỷ lệ cạnh QR)", 0.12, 0.30, float(s["qr_logo_ratio"]), 0.02)
        if st.form_submit_button("Lưu", type="primary"):
            with state.guard("Đã lưu cấu hình QR."):
                branding.save_settings(actor, {"qr_use_logo": use_logo, "qr_logo_source": source, "qr_color_mode": mode,
                                               "qr_logo_ratio": ratio})
    logo = branding.get_logo(s["qr_logo_source"]) if s["qr_use_logo"] else None
    res = qrimage.make_qr(qrcodes.payload_for("PREVIEW23456"), logo=logo, logo_ratio=float(s["qr_logo_ratio"]),
                          fg=s["primary_color"] if s["qr_color_mode"] == "brand" else "#000000")
    c1, c2 = st.columns([1, 2])
    c1.image(res.image, width=200)
    c2.markdown(f"**Kết quả tự kiểm tra:** {res.message}\n\n"
                "- Mức sửa lỗi **H** khi có logo (phục hồi ~30% dữ liệu).\n"
                "- Logo nằm trên nền trắng, không che ô định vị ở 3 góc.\n"
                "- Màu quá nhạt được tự làm tối để đủ tương phản.\n"
                "- Nếu không giải mã được, hệ thống tự giảm logo, rồi bỏ logo.")


def _rules(actor, s) -> None:
    with st.form("rules"):
        excused = st.checkbox("Tính 'Vắng có phép' như có mặt khi tính tỷ lệ chuyên cần", bool(s["excused_counts_as_attended"]))
        threshold = st.slider("Ngưỡng cảnh báo chuyên cần thấp (%)", 50, 100, int(s["low_attendance_threshold"]), 5)
        plain = st.checkbox("Chấp nhận QR cũ chỉ chứa mã thiếu nhi (tương thích thẻ in trước đây)",
                            bool(s["accept_plain_code_qr"]),
                            help="Kém an toàn hơn: ai biết mã số cũng tự tạo được QR. Chỉ bật trong giai đoạn chuyển đổi.")
        if st.form_submit_button("Lưu", type="primary"):
            with state.guard("Đã lưu quy tắc."):
                branding.save_settings(actor, {"excused_counts_as_attended": excused,
                                               "low_attendance_threshold": threshold, "accept_plain_code_qr": plain})


def _backup(actor) -> None:
    if not actor.can(P_BACKUP):
        st.info("Chỉ quản trị viên được sao lưu/khôi phục.")
        return
    st.markdown("Bản sao lưu gồm **toàn bộ dữ liệu** (thiếu nhi, điểm danh, tài khoản đã băm mật khẩu, cấu hình, logo). "
                "Hãy lưu file ở nơi an toàn – file chứa thông tin cá nhân của trẻ em.")
    if st.button("📦 Tạo bản sao lưu"):
        with state.guard():
            st.session_state["backup_blob"] = backup.export_backup(actor)
    if st.session_state.get("backup_blob"):
        st.download_button("⬇️ Tải bản sao lưu", st.session_state["backup_blob"],
                           f"tntt_backup_{date.today():%Y%m%d}.zip", mime="application/zip")
    st.divider()
    st.markdown("**Khôi phục** – thay thế TOÀN BỘ dữ liệu hiện tại bằng bản sao lưu.")
    up = st.file_uploader("Chọn file sao lưu (.zip)", type=["zip"], key="restore_up")
    if up:
        try:
            manifest = backup.read_manifest(up.getvalue())
        except ValueError as exc:
            st.error(str(exc))
            return
        st.json({"Tạo lúc (UTC)": manifest["created_at"], "Phiên bản": manifest["app_version"],
                 "Số thiếu nhi": manifest["counts"].get("students"),
                 "Số bản ghi điểm danh": manifest["counts"].get("attendance_records")})
        confirm = st.text_input("Gõ KHÔI PHỤC để xác nhận")
        if st.button("Khôi phục dữ liệu", type="primary", disabled=confirm.strip() != "KHÔI PHỤC"):
            with state.guard():
                backup.restore_backup(actor, up.getvalue())
                st.cache_data.clear()
                state.logout()
                state.flash("success", "Đã khôi phục dữ liệu. Vui lòng đăng nhập lại.")
                st.rerun()


def _face(actor, s) -> None:
    st.markdown("Nhận diện khuôn mặt là **module tùy chọn, mặc định tắt**. Dữ liệu khuôn mặt của trẻ em là dữ liệu "
                "sinh trắc học (dữ liệu cá nhân nhạy cảm). Hệ thống vẫn vận hành đầy đủ bằng QR và điểm danh thủ công.")
    allowed = config.face_module_allowed()
    ok, reason = face_svc.engine_status()
    st.markdown(f"- Cho phép ở cấp triển khai (`FACE_MODULE_ALLOWED`): **{'có' if allowed else 'không'}**\n"
                f"- Bộ máy nhận diện: **{reason}**\n"
                f"- Trạng thái module: **{'ĐANG BẬT' if face_svc.is_enabled(s) else 'tắt'}**")
    if not allowed:
        st.info("Để bật, người triển khai phải đặt `FACE_MODULE_ALLOWED = true` trong Secrets sau khi đã hoàn tất thủ tục "
                "pháp lý. Xem `docs/FACE_MODULE.md`.")
        return
    acked = list(s.get("face_conditions_ack") or [])
    with st.form("face_conditions"):
        st.markdown("**Xác nhận điều kiện trước khi bật**")
        checks = [st.checkbox(text, value=i < len(acked) and bool(acked[i]), key=f"fc_{i}")
                  for i, text in enumerate(face_svc.CONDITIONS)]
        enabled = st.toggle("Bật module khuôn mặt", bool(s["face_enabled"]))
        c1, c2 = st.columns(2)
        thr = c1.slider("Ngưỡng tương đồng tối thiểu", 0.35, 0.80, float(s["face_threshold"]), 0.01)
        margin = c2.slider("Khoảng cách tối thiểu với người giống thứ hai", 0.02, 0.20, float(s["face_margin"]), 0.01)
        if st.form_submit_button("Lưu", type="primary"):
            if enabled and not all(checks):
                st.error("Phải xác nhận đủ tất cả điều kiện mới được bật.")
                return
            with state.guard("Đã lưu."):
                branding.save_settings(actor, {"face_enabled": enabled, "face_conditions_ack": checks,
                                               "face_threshold": thr, "face_margin": margin})
                st.rerun()
    if not face_svc.is_enabled(s):
        return
    st.divider()
    st.markdown("**Đồng ý & đăng ký khuôn mặt từng em**")
    df = students.students_frame(state.year_id(), actor, status="active", include_unenrolled=False)
    if df.empty:
        return
    labels = {int(r.id): f"{r.code} · {r.full_name} · {r.class_name or ''}" for r in df.itertuples()}
    sid = st.selectbox("Thiếu nhi", list(labels), format_func=labels.get)
    info = face_svc.consent_overview([sid])[sid]
    st.caption(f"Đồng ý hợp lệ đến: **{info['consent'] or 'chưa có'}** · số mẫu khuôn mặt: **{info['templates']}**")
    with st.expander("Ghi nhận văn bản đồng ý"):
        with st.form("consent"):
            g = st.text_input("Họ tên cha/mẹ/người giám hộ")
            rel = st.selectbox("Quan hệ", ["Cha", "Mẹ", "Người giám hộ"])
            d1, d2 = st.columns(2)
            cd = d1.date_input("Ngày ký", date.today(), format="DD/MM/YYYY")
            ex = d2.date_input("Hết hạn", date.today() + timedelta(days=300), format="DD/MM/YYYY")
            ref = st.text_input("Số/mã văn bản lưu trữ")
            if st.form_submit_button("Lưu đồng ý"):
                with state.guard("Đã ghi nhận đồng ý."):
                    face_svc.record_consent(actor, sid, g, rel, cd, ex, ref)
                    st.rerun()
    if info["consent"] and ok:
        photo = st.camera_input("Chụp ảnh đăng ký (chỉ trích xuất đặc trưng, KHÔNG lưu ảnh)", key=f"enroll_{sid}")
        if photo and st.button("Đăng ký mẫu này"):
            with state.guard():
                try:
                    n = face_svc.enroll(actor, sid, photo.getvalue())
                    st.success(f"Đã lưu mẫu thứ {n}.")
                except PermissionError as exc:
                    st.error(str(exc))
    c1, c2, c3 = st.columns(3)
    if c1.button("Rút đồng ý & xóa dữ liệu của em này"):
        with state.guard("Đã rút đồng ý và xóa dữ liệu sinh trắc học."):
            face_svc.withdraw_consent(actor, sid)
            st.rerun()
    if c2.button("Xóa mẫu khuôn mặt của em này"):
        with state.guard("Đã xóa."):
            face_svc.delete_templates(actor, sid)
            st.rerun()
    with c3.popover("Xóa TOÀN BỘ dữ liệu khuôn mặt"):
        if st.button("Xác nhận xóa toàn bộ", type="primary"):
            with state.guard("Đã xóa toàn bộ dữ liệu sinh trắc học."):
                face_svc.delete_templates(actor, None)
                st.rerun()
