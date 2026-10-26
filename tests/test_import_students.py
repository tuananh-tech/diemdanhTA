import io
from pathlib import Path

import pandas as pd
import pytest

from tntt.security import PermissionDenied
from tntt.services import importer, org, students
from tntt.services.students import StudentInput

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "sample_data"


def _xlsx(df: pd.DataFrame, text_format=True) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
        if text_format:
            for col in w.sheets["Sheet1"].columns:
                for c in col:
                    c.number_format = "@"
    return buf.getvalue()


def _plan(data: bytes, filename: str, **opts):
    raw = importer.read_raw(data, filename)
    df = importer.table_from_raw(raw, importer.detect_header_row(raw))
    mapping = importer.auto_map(list(df.columns))
    return importer.build_plan(df, mapping, importer.ImportOptions(**opts)), mapping


def test_import_simple_id_ten_with_saint_split(admin, year):
    data = (SAMPLES / "mau_don_gian_ID_Ten.xlsx").read_bytes()
    plan, mapping = _plan(data, "mau.xlsx", split_saint=True)
    assert mapping["code"] == "ID" and mapping["full_name"] == "Tên"
    assert plan.counts()["create"] == 24 and plan.counts()["error"] == 0
    first = plan.rows[0].data
    assert first.saint_name and first.full_name and first.saint_name not in first.full_name
    res = importer.apply_plan(admin, plan, year.id)
    assert res["created"] == 24
    df = students.students_frame(year.id, admin)
    assert len(df) == 24


def test_import_full_template_creates_classes_and_keeps_zeros(admin, year):
    data = (SAMPLES / "mau_day_du_120_em.xlsx").read_bytes()
    plan, mapping = _plan(data, "full.xlsx")
    assert {"code", "saint_name", "full_name", "birth_date", "branch", "class_name", "team"} <= set(mapping)
    res = importer.apply_plan(admin, plan, year.id)
    assert res["created"] == 120 and res["classes_created"] == 6
    df = students.students_frame(year.id, admin)
    assert df["code"].iloc[0].startswith("0") and len(df["code"].iloc[0]) == 4
    assert set(df["class_name"]) == {"Chiên Con A", "Ấu Nhi 1", "Ấu Nhi 2", "Thiếu Nhi 1", "Thiếu Nhi 2", "Nghĩa Sĩ 1"}
    assert df["birth_date"].notna().all()


def test_csv_leading_zero_and_pad_option(admin, year):
    data = (SAMPLES / "mau_csv_so_0_dau.csv").read_bytes()
    plan, _ = _plan(data, "a.csv")
    assert plan.rows[0].data.code == "0001"
    # Excel đã lưu mã dạng SỐ (mất 0) -> tùy chọn bù số 0
    num = _xlsx(pd.DataFrame({"Mã": [1, 2, 30], "Họ tên": ["A Văn", "B Thị", "C Văn"]}), text_format=False)
    plan2, _ = _plan(num, "n.xlsx", pad_code_width=4)
    assert [r.data.code for r in plan2.rows] == ["0001", "0002", "0030"]


def test_validation_duplicates_and_bad_dates(admin, year):
    df = pd.DataFrame({"Mã": ["01", "01", "02", ""], "Họ và tên": ["An", "Bình", "", "Chi"],
                       "Ngày sinh": ["01/01/2015", "99/99/2015", "", ""]})
    plan, _ = _plan(_xlsx(df), "x.xlsx", auto_code=True)
    actions = [r.action for r in plan.rows]
    assert actions[0] == "create"
    assert actions[1] == "error"  # trùng mã + ngày sai
    assert actions[2] == "error"  # thiếu tên
    assert plan.rows[3].action == "create" and "Tự sinh mã" in plan.rows[3].warnings


def test_upsert_updates_without_erasing_and_keeps_history(admin, year):
    data = _xlsx(pd.DataFrame({"Mã": ["0001"], "Tên Thánh": ["Maria"], "Họ và tên": ["Lê Thị Hoa"],
                               "SĐT phụ huynh": ["0901111222"], "Lớp": ["Ấu Nhi 1"]}))
    importer.apply_plan(admin, _plan(data, "a.xlsx")[0], year.id)
    # lần 2: không có cột SĐT, đổi tên Thánh -> chỉ cập nhật trường có giá trị
    data2 = _xlsx(pd.DataFrame({"Mã": ["0001"], "Tên Thánh": ["Anna"], "Họ và tên": ["Lê Thị Hoa"]}))
    plan2, _ = _plan(data2, "b.xlsx")
    assert plan2.rows[0].action == "update"
    importer.apply_plan(admin, plan2, year.id)
    st = students.find_by_code("0001")
    assert st.saint_name == "Anna" and st.parent_phone == "0901111222"
    enr = students.get_enrollment(st.id, year.id)
    assert enr.class_id is not None  # lớp cũ giữ nguyên


def test_create_only_mode_skips_existing(admin, year):
    data = _xlsx(pd.DataFrame({"Mã": ["0001"], "Họ và tên": ["Lê Hoa"]}))
    importer.apply_plan(admin, _plan(data, "a.xlsx")[0], year.id)
    data2 = _xlsx(pd.DataFrame({"Mã": ["0001"], "Họ và tên": ["Lê Hoa Đổi"]}))
    plan, _ = _plan(data2, "b.xlsx", update_existing=False)
    assert plan.rows[0].action == "unchanged"
    importer.apply_plan(admin, plan, year.id)
    assert students.find_by_code("0001").full_name == "Lê Hoa"


def test_separate_ho_ten_columns():
    df = pd.DataFrame({"STT": ["1"], "Họ": ["Nguyễn Văn"], "Tên": ["An"]})
    raw = importer.read_raw(_xlsx(df), "x.xlsx")
    tbl = importer.table_from_raw(raw, importer.detect_header_row(raw))
    mapping = importer.auto_map(list(tbl.columns))
    assert mapping.get("family_name") == "Họ" and mapping.get("given_name") == "Tên"


def test_real_user_book1_if_present(admin, year):
    """Đọc file Book1.xlsx gốc của người dùng (nếu có trên máy) – không đưa vào repo."""
    real = ROOT.parent / "New" / "Book1.xlsx"
    if not real.exists():
        pytest.skip("Không có Book1.xlsx trên máy này")
    plan, mapping = _plan(real.read_bytes(), "Book1.xlsx", split_saint=True)
    assert plan.counts()["error"] == 0 and len(plan.rows) == 24


def test_search_unaccented_transfer_and_promote(admin, school):
    y = school["year"]
    df = students.students_frame(y.id, admin, search="nguyen van em1")
    assert set(df["code"]) >= {"0001"}
    df2 = students.students_frame(y.id, admin, search="EM10")
    assert list(df2["code"]) == ["0010"]
    sid = school["students"][school["c1"]][0]
    students.transfer_students(admin, [sid], y.id, school["c2"])
    assert students.get_enrollment(sid, y.id).class_id == school["c2"]
    # chuyển năm học
    from datetime import date
    y2 = org.save_year(admin, "2099-2100", date(2099, 8, 1), date(2100, 7, 31), None, make_current=False)
    nc1 = org.save_class(admin, y2, "Ấu Nhi 2", school["branches"]["Ấu Nhi"])
    nc2 = org.save_class(admin, y2, "Thiếu Nhi 2", school["branches"]["Thiếu Nhi"])
    res = students.promote_year(admin, y.id, y2, {school["c1"]: nc1, school["c2"]: nc2})
    assert res["created"] == 10 and res["skipped_inactive"] == 1
    hist = students.enrollment_history(sid)
    assert list(hist["Năm học"]) == ["2099-2100", y.name]  # lịch sử năm cũ còn nguyên


def test_leader_scope_on_students(leader, school, admin):
    y = school["year"]
    visible = students.students_frame(y.id, leader)
    assert set(visible["class_id"]) == {school["c1"]}
    other = school["students"][school["c2"]][0]
    with pytest.raises(PermissionDenied):
        students.save_student(leader, StudentInput(code="0006", full_name="Đổi Tên"), y.id, school["c2"],
                              student_id=other)
    with pytest.raises(PermissionDenied):
        students.transfer_students(leader, [school["students"][school["c1"]][0]], y.id, school["c2"])


def test_duplicate_code_rejected(admin, school):
    with pytest.raises(ValueError):
        students.save_student(admin, StudentInput(code="0001", full_name="Trùng"), school["year"].id, None)
