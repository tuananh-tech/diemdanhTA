"""Thiếu nhi: danh sách, thêm/sửa, chuyển lớp, nhập Excel, xuất Excel, chuyển năm học."""
from __future__ import annotations

import hashlib
from datetime import date

import pandas as pd
import streamlit as st

from ... import constants as C
from ...security import P_STUDENTS_EDIT, P_STUDENTS_IMPORT, P_USERS
from ...services import attendance, branding, importer, org, reports, students
from ...services.students import StudentInput
from .. import state


def render() -> None:
    actor = state.actor()
    year = state.year()
    st.title("Thiếu nhi")
    tabs = ["📋 Danh sách"]
    if actor.can(P_STUDENTS_IMPORT):
        tabs += ["📥 Nhập Excel"]
    if actor.is_global:
        tabs += ["🎓 Chuyển năm học"]
    t = st.tabs(tabs, key="tabs_students")
    with t[0]:
        _list(actor, year)
    if actor.can(P_STUDENTS_IMPORT):
        with t[1]:
            _import(actor, year)
    if actor.is_global:
        with t[-1]:
            _promote(actor, year)


# ---------------------------------------------------------------------------
def _list(actor, year) -> None:
    branches = {b.id: b.name for b in org.list_branches()}
    copts = org.class_options(year.id, actor)
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    search = c1.text_input("Tìm theo tên hoặc mã (không dấu được)", key="stu_q")
    branch = c2.selectbox("Ngành", [None, *branches], format_func=lambda b: "Tất cả" if b is None else branches[b],
                          key="stu_branch")
    cls = c3.selectbox("Lớp", [None, *copts], format_func=lambda c: "Tất cả" if c is None else copts[c], key="stu_cls")
    status = c4.selectbox("Tình trạng", [None, *C.STUDENT_STATUS_LABELS],
                          format_func=lambda s: "Tất cả" if s is None else C.STUDENT_STATUS_LABELS[s], key="stu_status")
    df = students.students_frame(year.id, actor, branch_id=branch, class_id=cls, status=status, search=search)

    a1, a2, a3 = st.columns([1, 1, 2])
    if actor.can(P_STUDENTS_EDIT) and a1.button("➕ Thêm thiếu nhi", type="primary"):
        _edit_dialog(actor, year, None)
    if not df.empty:
        a2.download_button("⬇️ Xuất Excel", _export(df, year), f"thieu_nhi_{year.name}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    a3.caption(f"{len(df)} em · năm học {year.name}")
    if df.empty:
        st.info("Chưa có thiếu nhi phù hợp. Dùng **Nhập Excel** hoặc **Thêm thiếu nhi**.")
        return
    view = pd.DataFrame({
        "Mã": df.code, "Tên Thánh": df.saint_name.fillna(""), "Họ và tên": df.full_name,
        "Ngày sinh": df.birth_date.map(lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) and d else ""),
        "Lớp": df.class_name.fillna("—"), "Ngành": df.branch.fillna(""), "Đội": df.team.fillna(""),
        "Tình trạng": df.status.map(C.STUDENT_STATUS_LABELS), "QR": df.qr_active.map(lambda v: "✓" if v else ""),
    })
    event = st.dataframe(view, hide_index=True, on_select="rerun", selection_mode="multi-row", key="stu_table",
                         height=min(600, 38 + 35 * len(view)))
    rows = event.selection.rows if event and event.selection else []
    if not rows:
        st.caption("Chọn 1 dòng để xem/sửa; chọn nhiều dòng để chuyển lớp hoặc đổi tình trạng.")
        return
    selected = df.iloc[rows]
    if len(selected) == 1:
        _detail(actor, year, selected.iloc[0])
    if actor.can(P_STUDENTS_EDIT):
        _bulk(actor, year, selected, copts)


def _detail(actor, year, row) -> None:
    with st.container(border=True):
        st.subheader(f"{row.saint_name or ''} {row.full_name}".strip())
        st.caption(f"Mã {row.code} · {row.class_name or 'chưa xếp lớp'} · {C.STUDENT_STATUS_LABELS[row.status]}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Lịch sử ghi danh**")
            st.dataframe(students.enrollment_history(int(row.id)), hide_index=True)
        with c2:
            st.markdown("**Điểm danh năm học này**")
            hist = attendance.student_session_summary(int(row.id), year.id)
            if hist.empty:
                st.caption("Chưa có.")
            else:
                summ = reports.summarize(hist.assign(session_id=range(len(hist)), student_id=row.id),
                                         bool(branding.get_settings()["excused_counts_as_attended"]))
                st.metric("Chuyên cần", "—" if summ["rate"] is None else f"{summ['rate']:.1f}%",
                          help="(Có mặt + Trễ) / số buổi đã có kết quả")
                st.dataframe(pd.DataFrame({"Ngày": hist.date.map(lambda d: d.strftime("%d/%m")), "Buổi": hist.title,
                                           "Trạng thái": hist.status.map(C.STATUS_LABELS)}), hide_index=True, height=220)
        b1, b2 = st.columns(2)
        if actor.can(P_STUDENTS_EDIT) and b1.button("✏️ Sửa thông tin", key=f"edit_{row.id}"):
            _edit_dialog(actor, year, row)
        if actor.can(P_USERS):
            with b2.popover("🗑️ Xóa"):
                st.caption("Chỉ xóa được khi em chưa có dữ liệu điểm danh. Nếu đã có, hãy đổi tình trạng.")
                if st.button("Xóa vĩnh viễn", key=f"del_{row.id}", type="primary"):
                    with state.guard():
                        students.delete_student(actor, int(row.id))
                        state.flash("success", "Đã xóa.")
                        st.rerun()


def _bulk(actor, year, selected, copts) -> None:
    with st.expander(f"Thao tác cho {len(selected)} em đã chọn", expanded=len(selected) > 1):
        c1, c2 = st.columns(2)
        with c1:
            target = st.selectbox("Chuyển sang lớp", list(copts), format_func=copts.get, key="bulk_cls")
            if st.button("Chuyển lớp", key="bulk_move", disabled=not copts):
                with state.guard():
                    n = students.transfer_students(actor, [int(i) for i in selected.id], year.id, target)
                    state.flash("success", f"Đã chuyển {n} em sang {copts[target]}. Lịch sử các buổi đã điểm danh giữ nguyên.")
                    st.rerun()
        with c2:
            stt = st.selectbox("Đổi tình trạng", list(C.STUDENT_STATUS_LABELS), format_func=C.STUDENT_STATUS_LABELS.get,
                               key="bulk_st")
            if st.button("Cập nhật tình trạng", key="bulk_status"):
                with state.guard():
                    students.set_status(actor, [int(i) for i in selected.id], stt, year.id)
                    state.flash("success", "Đã cập nhật.")
                    st.rerun()


@st.dialog("Thông tin thiếu nhi", width="large")
def _edit_dialog(actor, year, row) -> None:
    copts = org.class_options(year.id, actor)
    enr_class = int(row.class_id) if row is not None and pd.notna(row.class_id) else None
    with st.form("student_form"):
        c1, c2 = st.columns(2)
        code = c1.text_input("Mã thiếu nhi *", value=row.code if row is not None else students.next_code(),
                             help="Giữ nguyên số 0 ở đầu. Không trùng.")
        saint = c2.text_input("Tên Thánh", value=(row.saint_name or "") if row is not None else "")
        full = st.text_input("Họ và tên *", value=row.full_name if row is not None else "")
        c3, c4, c5 = st.columns(3)
        birth = c3.date_input("Ngày sinh", value=row.birth_date if row is not None and pd.notna(row.birth_date) else None,
                              min_value=date(1950, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
        genders = ["", "M", "F"]
        gender = c4.selectbox("Giới tính", genders, format_func=C.GENDER_LABELS.get,
                              index=genders.index(row.gender) if row is not None and row.gender in genders else 0)
        statuses = list(C.STUDENT_STATUS_LABELS)
        status = c5.selectbox("Tình trạng", statuses, format_func=C.STUDENT_STATUS_LABELS.get,
                              index=statuses.index(row.status) if row is not None else 0)
        c6, c7 = st.columns(2)
        cls_options = ([None] if actor.is_global else []) + list(copts)
        cls = c6.selectbox("Lớp (năm học đang chọn)", cls_options,
                           format_func=lambda c: "— Chưa xếp lớp —" if c is None else copts[c],
                           index=cls_options.index(enr_class) if enr_class in cls_options else 0)
        team = c7.text_input("Đội", value=(row.team or "") if row is not None else "")
        c8, c9 = st.columns(2)
        parent = c8.text_input("Phụ huynh", value=(row.parent_name or "") if row is not None else "")
        phone = c9.text_input("SĐT phụ huynh", value=(row.parent_phone or "") if row is not None else "")
        note = st.text_input("Ghi chú", value=(row.note or "") if row is not None else "", max_chars=255)
        ok = st.form_submit_button("Lưu", type="primary")
    if ok:
        with state.guard():
            students.save_student(actor, StudentInput(code=code, full_name=full, saint_name=saint, birth_date=birth,
                                                      gender=gender, parent_name=parent, parent_phone=phone, note=note,
                                                      status=status),
                                  year.id, cls, team, student_id=int(row.id) if row is not None else None)
            state.flash("success", "Đã lưu thông tin thiếu nhi.")
            st.rerun()


def _export(df: pd.DataFrame, year) -> bytes:
    out = pd.DataFrame({
        "Mã thiếu nhi": df.code, "Tên Thánh": df.saint_name.fillna(""), "Họ và tên": df.full_name,
        "Ngày sinh": df.birth_date.map(lambda d: d.strftime("%d/%m/%Y") if pd.notna(d) and d else ""),
        "Giới tính": df.gender.fillna("").map(C.GENDER_LABELS).fillna(""), "Ngành": df.branch.fillna(""),
        "Lớp": df.class_name.fillna(""), "Đội": df.team.fillna(""), "Năm học": year.name,
        "Tình trạng": df.status.map(C.STUDENT_STATUS_LABELS), "Phụ huynh": df.parent_name.fillna(""),
        "SĐT phụ huynh": df.parent_phone.fillna(""), "Ghi chú": df.note.fillna(""),
    })
    s = branding.get_settings()
    return reports.to_excel({"Thiếu nhi": out}, title="Danh sách thiếu nhi", subtitle=f"Năm học {year.name}",
                            org_name=f"{s['xudoan_name']} – {s['parish_name']}")


# ---------------------------------------------------------------------------
def _import(actor, year) -> None:
    st.markdown("**Bước 1.** Tải file `.xlsx`, `.xls` hoặc `.csv`. File chỉ cần 2 cột *ID* và *Tên* cũng được.")
    st.download_button("⬇️ Tải file mẫu", importer.template_bytes(), "mau_nhap_thieu_nhi.xlsx")
    up = st.file_uploader("Chọn file", type=["xlsx", "xls", "csv"], key="imp_file")
    if not up:
        return
    data = up.getvalue()
    digest = hashlib.sha1(data).hexdigest()[:10]
    try:
        sheets = importer.list_sheets(data, up.name)
        sheet = st.selectbox("Trang tính", sheets) if len(sheets) > 1 else sheets[0]
        raw = importer.read_raw(data, up.name, None if sheet == "CSV" else sheet)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Không đọc được file: {exc}")
        return
    if raw.empty:
        st.warning("File trống.")
        return
    hdr = st.number_input("Dòng tiêu đề (tự nhận diện)", 1, min(20, len(raw)), importer.detect_header_row(raw) + 1,
                          key=f"hdr_{digest}") - 1
    df = importer.table_from_raw(raw, hdr)
    st.markdown("**Bước 2.** Kiểm tra cách hiểu các cột.")
    auto = importer.auto_map(list(df.columns))
    cols = [importer.IGNORE, *df.columns]
    mapping = {}
    grid = st.columns(3)
    for i, (fld, (label, _)) in enumerate(importer.FIELDS.items()):
        default = auto.get(fld, importer.IGNORE)
        choice = grid[i % 3].selectbox(label, cols, index=cols.index(default), key=f"map_{digest}_{fld}")
        if choice != importer.IGNORE:
            mapping[fld] = choice
    with st.expander("Xem dữ liệu gốc (20 dòng đầu)"):
        st.dataframe(df.head(20), hide_index=True)

    st.markdown("**Bước 3.** Tùy chọn.")
    o1, o2, o3 = st.columns(3)
    has_saint_col = "saint_name" in mapping
    opts = importer.ImportOptions(
        split_saint=o1.checkbox("Tách Tên Thánh khỏi cột họ tên", value=not has_saint_col, disabled=has_saint_col,
                                help="Ví dụ 'Maria Nguyễn Thị A' → Tên Thánh 'Maria'."),
        title_case=o1.checkbox("Chuẩn hóa viết hoa họ tên"),
        auto_code=o2.checkbox("Tự sinh mã cho dòng thiếu mã", value=True),
        pad_code_width=int(o2.number_input("Bù số 0 cho mã số đến (chữ số, 0 = không)", 0, 10, 0,
                                           help="Dùng khi Excel đã làm mất số 0 ở đầu, ví dụ 7 → 0007.")),
        update_existing=o3.radio("Mã đã tồn tại", [True, False], horizontal=False,
                                 format_func=lambda v: "Cập nhật (chỉ ô có dữ liệu)" if v else "Bỏ qua, chỉ thêm mới"),
    )
    copts = org.class_options(year.id)
    branches = {b.id: b.name for b in org.list_branches()}
    d1, d2 = st.columns(2)
    default_class = None
    if "class_name" not in mapping:
        default_class = d1.selectbox("Xếp tất cả vào lớp", [None, *copts],
                                     format_func=lambda c: "— Không xếp lớp —" if c is None else copts[c])
    default_branch = d2.selectbox("Ngành mặc định cho lớp mới tạo", [None, *branches],
                                  format_func=lambda b: "— Không —" if b is None else branches[b]) \
        if "class_name" in mapping and "branch" not in mapping else None

    try:
        plan = importer.build_plan(df, mapping, opts)
    except ValueError as exc:
        st.warning(str(exc))
        return
    counts = plan.counts()
    st.markdown("**Bước 4.** Xem trước kết quả.")
    m = st.columns(4)
    m[0].metric("Thêm mới", counts["create"])
    m[1].metric("Cập nhật", counts["update"])
    m[2].metric("Không đổi", counts["unchanged"])
    m[3].metric("Lỗi (sẽ bỏ qua)", counts["error"])
    preview = plan.to_frame()
    only_issues = st.toggle("Chỉ hiện dòng có lỗi/cảnh báo/thay đổi")
    if only_issues:
        preview = preview[preview["Ghi chú kiểm tra"] != ""]
    st.dataframe(preview, hide_index=True, height=min(500, 38 + 35 * len(preview)))
    if counts["error"]:
        st.warning(f"{counts['error']} dòng lỗi sẽ KHÔNG được nhập. Sửa file rồi tải lại nếu cần.")
    if st.button(f"✅ Nhập {counts['create']} mới, cập nhật {counts['update']} vào năm học {year.name}", type="primary",
                 disabled=(counts["create"] + counts["update"] + counts["unchanged"]) == 0):
        with state.guard():
            res = importer.apply_plan(actor, plan, year.id, default_class, default_branch, filename=up.name)
            state.flash("success", f"Đã nhập: thêm {res['created']}, cập nhật {res['updated']}, ghi danh {res['enrolled']}, "
                                   f"tạo {res['classes_created']} lớp mới, bỏ qua {res['skipped_errors']} dòng lỗi.")
            st.rerun()


# ---------------------------------------------------------------------------
def _promote(actor, year) -> None:
    st.caption("Tạo ghi danh cho năm học mới từ năm học cũ. Hồ sơ và lịch sử năm cũ được giữ nguyên.")
    years = org.list_years()
    if len(years) < 2:
        st.info("Cần tạo năm học mới (trang **Ngành / Lớp**) và các lớp của năm đó trước.")
        return
    names = {y.id: y.name for y in years}
    c1, c2 = st.columns(2)
    src = c1.selectbox("Từ năm học", list(names), format_func=names.get, index=min(1, len(years) - 1))
    dst = c2.selectbox("Sang năm học", list(names), format_func=names.get, index=0)
    if src == dst:
        st.warning("Chọn hai năm học khác nhau.")
        return
    src_classes = org.classes_frame(src)
    dst_opts = org.class_options(dst)
    if not dst_opts:
        st.info("Năm học đích chưa có lớp.")
        return
    st.markdown("**Ánh xạ lớp** (lớp cũ → lớp mới; chọn “Không chuyển” để bỏ qua lớp đó)")
    mapping = {}
    for r in src_classes.itertuples():
        guess = next((k for k, v in dst_opts.items() if v.split(" · ")[0] == r.name), None)
        choices = [None, *dst_opts]
        mapping[int(r.id)] = st.selectbox(f"{r.name} ({r.students} em)", choices,
                                          index=choices.index(guess) if guess in choices else 0,
                                          format_func=lambda c: "— Không chuyển —" if c is None else dst_opts[c],
                                          key=f"pm_{src}_{dst}_{r.id}")
    only_active = st.checkbox("Chỉ chuyển các em đang sinh hoạt", value=True)
    if st.button("Thực hiện chuyển năm học", type="primary"):
        with state.guard():
            res = students.promote_year(actor, src, dst, mapping, only_active=only_active)
            state.flash("success", f"Đã ghi danh {res['created']} em; bỏ qua {res['skipped_existing']} em đã có, "
                                   f"{res['skipped_unmapped']} em không ánh xạ, {res['skipped_inactive']} em không sinh hoạt.")
            st.rerun()


