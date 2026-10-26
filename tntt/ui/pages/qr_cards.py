"""Thẻ QR: tạo/xem trước QR có logo, tải đơn lẻ/hàng loạt, in thẻ PDF, thu hồi/cấp lại."""
from __future__ import annotations

import streamlit as st

from ... import cards, qrimage
from ...services import branding, org, qrcodes, students
from .. import state


def _style_controls(settings: dict):
    c1, c2, c3 = st.columns(3)
    use_logo = c1.toggle("QR có logo ở giữa", value=bool(settings["qr_use_logo"]))
    color_mode = c2.radio("Màu QR", ["bw", "brand"], index=0 if settings["qr_color_mode"] == "bw" else 1,
                          format_func={"bw": "Trắng đen", "brand": "Màu nhận diện"}.get, horizontal=True)
    ratio = c3.slider("Kích thước logo", 0.12, 0.30, float(settings["qr_logo_ratio"]), 0.02, disabled=not use_logo,
                      help="Giới hạn an toàn 12–30% cạnh QR. Hệ thống tự giảm nếu mã khó quét.")
    logo = branding.get_logo(settings["qr_logo_source"]) if use_logo else None
    fg = settings["primary_color"] if color_mode == "brand" else "#000000"
    return logo, ratio, fg


def render() -> None:
    actor = state.actor()
    year = state.year()
    settings = branding.get_settings()
    st.title("Thẻ QR")
    st.caption("Nội dung QR chỉ là một mã ngẫu nhiên (ví dụ `TNTT:K7P2…`), không chứa họ tên, ngày sinh hay thông tin "
               "cá nhân. Mã chỉ có ý nghĩa khi quét bằng hệ thống này sau khi đăng nhập.")
    logo, ratio, fg = _style_controls(settings)

    copts = org.class_options(year.id, actor)
    c1, c2 = st.columns([1, 2])
    cls = c1.selectbox("Lớp", [None, *copts], format_func=lambda c: "Tất cả (trong phạm vi)" if c is None else copts[c])
    df = students.students_frame(year.id, actor, class_id=cls, status="active", include_unenrolled=False)
    if df.empty:
        st.info("Không có thiếu nhi đang sinh hoạt trong lựa chọn này.")
        return
    labels = {int(r.id): f"{r.code} · {r.saint_name or ''} {r.full_name} · {r.class_name or ''}" for r in df.itertuples()}
    picked = c2.multiselect("Chọn em (để trống = tất cả trong danh sách)", list(labels), format_func=labels.get)
    ids = picked or list(labels)
    st.caption(f"Sẽ xử lý **{len(ids)}** em.")

    t1, t2, t3 = st.tabs(["👁️ Xem trước & tải 1 mã", "🖨️ In thẻ PDF / tải hàng loạt", "♻️ Thu hồi / cấp lại"], key="tabs_qr")
    with t1:
        one = st.selectbox("Thiếu nhi", ids, format_func=labels.get, key="qr_one")
        if st.button("Tạo / xem QR", type="primary"):
            with state.guard():
                token = qrcodes.ensure_tokens(actor, [one], year.id)[one]
                res = qrimage.make_qr(qrcodes.payload_for(token), logo=logo, logo_ratio=ratio, fg=fg, module_px=16)
                row = df[df.id == one].iloc[0]
                card = cards.CardData(row.code, row.saint_name or "", row.full_name, row.class_name or "",
                                      row.branch or "", res.payload)
                a, b = st.columns([1, 1.3])
                a.image(cards.labeled(res.image, card), width="stretch")
                (b.success if res.verified else b.warning)(res.message)
                b.markdown(f"- Mức sửa lỗi: **{'H' if res.logo_requested else 'M'}** · version {res.version}\n"
                           f"- Logo: **{'có, ' + format(res.logo_ratio, '.0%') if res.logo_applied else 'không'}**\n"
                           f"- Đã tự kiểm tra giải mã: **{'đạt' if res.verified else 'CHƯA đạt'}** "
                           f"({', '.join(qrimage.available_decoders()) or 'không có bộ giải mã'})")
                b.download_button("⬇️ Tải PNG (có tên)", qrimage.to_png(cards.labeled(res.image, card)),
                                  f"QR_{cards.safe_filename(row.code)}_{cards.safe_filename(row.full_name)}.png")
                b.download_button("⬇️ Tải PNG (chỉ mã)", qrimage.to_png(res.image),
                                  f"QR_{cards.safe_filename(row.code)}.png")
    with t2:
        st.markdown("Thẻ khổ **54 × 85,6 mm** (cỡ thẻ ATM, dọc), **9 thẻ/trang A4**, có vạch cắt. "
                    "In ở chế độ *Actual size / 100%*, không chọn *Fit to page*.")
        c1, c2 = st.columns(2)
        if c1.button("🖨️ Tạo PDF thẻ thiếu nhi", type="primary"):
            with state.guard():
                tokens = qrcodes.ensure_tokens(actor, ids, year.id)
                rows = df.set_index("id").loc[ids]
                data = [cards.CardData(r.code, r.saint_name or "", r.full_name, r.class_name or "", r.branch or "",
                                       qrcodes.payload_for(tokens[int(i)])) for i, r in rows.iterrows()]
                style = cards.CardStyle(settings["xudoan_name"], settings["parish_name"], year.name,
                                        primary=settings["primary_color"], accent=settings["accent_color"], fg=fg,
                                        logo=branding.get_logo(), qr_logo=logo, qr_logo_ratio=ratio)
                bar = st.progress(0.0, text="Đang tạo và kiểm tra từng mã…")
                rep = cards.build_cards_pdf(data, style, progress=lambda p: bar.progress(p, text=f"{p:.0%}"))
                bar.empty()
                st.session_state["cards_pdf"] = rep.pdf
                msg = f"Đã tạo {rep.total} thẻ."
                if rep.without_logo:
                    msg += f" {len(rep.without_logo)} mã phải bỏ logo để bảo đảm quét được."
                (st.warning if rep.unverified else st.success)(
                    msg + (f" CẢNH BÁO: {len(rep.unverified)} mã chưa tự kiểm tra được: {', '.join(rep.unverified[:10])}"
                           if rep.unverified else " Tất cả mã đã được giải mã thử thành công."))
        if st.session_state.get("cards_pdf"):
            c1.download_button("⬇️ Tải PDF thẻ", st.session_state["cards_pdf"], f"the_thieu_nhi_{year.name}.pdf",
                               mime="application/pdf")
        with_label = c2.checkbox("Ảnh có kèm tên bên dưới", value=True)
        if c2.button("🗜️ Tạo ZIP ảnh QR"):
            with state.guard():
                tokens = qrcodes.ensure_tokens(actor, ids, year.id)
                rows = df.set_index("id").loc[ids]
                data = [cards.CardData(r.code, r.saint_name or "", r.full_name, r.class_name or "", r.branch or "",
                                       qrcodes.payload_for(tokens[int(i)])) for i, r in rows.iterrows()]
                bar = st.progress(0.0)
                blob, problems = cards.build_qr_zip(data, logo=logo, logo_ratio=ratio, fg=fg, with_label=with_label,
                                                    progress=bar.progress)
                bar.empty()
                st.session_state["qr_zip"] = blob
                (st.warning if problems else st.success)(f"Đã tạo {len(data)} ảnh." +
                                                         (f" Chưa kiểm tra được: {problems}" if problems else ""))
        if st.session_state.get("qr_zip"):
            c2.download_button("⬇️ Tải ZIP", st.session_state["qr_zip"], f"qr_{year.name}.zip", mime="application/zip")
    with t3:
        st.markdown("Khi thẻ bị **mất, hỏng hoặc bị người khác dùng**, hãy cấp lại: mã cũ bị vô hiệu ngay, "
                    "quét mã cũ sẽ báo *đã thu hồi*.")
        one = st.selectbox("Thiếu nhi", ids, format_func=labels.get, key="qr_re")
        reason = st.text_input("Lý do", placeholder="Mất thẻ")
        c1, c2 = st.columns(2)
        if c1.button("♻️ Thu hồi & cấp mã mới", type="primary"):
            with state.guard("Đã cấp mã mới. Hãy in lại thẻ cho em."):
                qrcodes.reissue(actor, one, reason or "Cấp lại", year.id)
        if c2.button("⛔ Chỉ thu hồi (không cấp mới)"):
            with state.guard("Đã thu hồi."):
                qrcodes.revoke(actor, one, reason or "Thu hồi", year.id)
        st.markdown("**Lịch sử mã**")
        st.dataframe(qrcodes.history(one).rename(columns={
            "token": "Mã (che bớt)", "status": "Trạng thái", "issued_at": "Cấp lúc (UTC)", "issued_by": "Người cấp",
            "revoked_at": "Thu hồi lúc (UTC)", "reason": "Lý do"}), hide_index=True)
