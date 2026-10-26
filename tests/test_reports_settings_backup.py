import io
from datetime import date

import pandas as pd
import pytest
from PIL import Image

from tntt import constants as C
from tntt import db
from tntt.security import PermissionDenied
from tntt.services import attendance, backup, branding, org, reports, students, users

from .conftest import make_session


def _mark(admin, sid, statuses):
    roster = attendance.roster_frame(sid)
    for rid, st in zip(roster.record_id, statuses):
        if st != C.UNMARKED:
            assert attendance.set_status(admin, int(rid), st).ok


def test_attendance_rate_formula(admin, school):
    y = school["year"]
    s1 = make_session(admin, school, classes=[school["c1"]], session_date=date.today())
    _mark(admin, s1, [C.PRESENT, C.LATE, C.EXCUSED, C.ABSENT, C.UNMARKED])
    df = reports.attendance_frame(y.id, admin)
    summ = reports.summarize(df)
    assert summ["marked"] == 4 and summ["attended"] == 2 and summ["rate"] == pytest.approx(50.0)
    assert summ[C.UNMARKED] == 1  # chưa điểm danh không vào mẫu số
    summ2 = reports.summarize(df, excused_attended=True)
    assert summ2["rate"] == pytest.approx(75.0)


def test_rate_only_counts_eligible_sessions(admin, school):
    y = school["year"]
    only1 = make_session(admin, school, classes=[school["c1"]])
    both = make_session(admin, school)
    _mark(admin, only1, [C.PRESENT] * 5)
    roster = attendance.roster_frame(both)
    for rid in roster.record_id:
        attendance.set_status(admin, int(rid), C.ABSENT)
    st = reports.student_stats(reports.attendance_frame(y.id, admin))
    lop1 = st[st["class_name"] == "Ấu Nhi 1"].iloc[0]
    lop2 = st[st["class_name"] == "Thiếu Nhi 1"].iloc[0]
    assert lop1["records"] == 2 and lop1["rate"] == 50.0
    assert lop2["records"] == 1 and lop2["rate"] == 0.0  # lớp 2 không bị tính phiên chỉ dành cho lớp 1


def test_group_by_period_class_activity_and_exports(admin, school):
    y = school["year"]
    s1 = make_session(admin, school, title="Thánh lễ", activity_type="Thánh lễ")
    _mark(admin, s1, [C.PRESENT] * 6 + [C.ABSENT] * 4)
    df = reports.attendance_frame(y.id, admin)
    for period in ("day", "week", "month", "semester", "year"):
        g = reports.group_stats(reports.add_period(df, period, y), "period")
        assert int(g["records"].sum()) == 10
    by_class = reports.group_stats(df, "class_name")
    assert set(by_class["class_name"]) == {"Ấu Nhi 1", "Thiếu Nhi 1"}
    by_type = reports.group_stats(df, "activity_type")
    assert list(by_type["activity_type"]) == ["Thánh lễ"]
    matrix = reports.attendance_matrix(df)
    assert len(matrix) == 10 and "✓" in matrix.iloc[0].tolist()
    xlsx = reports.to_excel({"Tổng hợp": reports.pretty(by_class), "Sổ điểm danh": matrix},
                            title="Báo cáo", subtitle="Test", org_name="Xứ đoàn")
    back = pd.read_excel(io.BytesIO(xlsx), sheet_name=None, header=4)
    assert set(back) == {"Tổng hợp", "Sổ điểm danh"}
    csv = reports.to_csv(reports.pretty(by_class))
    assert csv.startswith(b"\xef\xbb\xbf") and "Chuyên cần".encode() in csv
    pdf = reports.to_pdf(title="Báo cáo chuyên cần", subtitle="Kiểm thử", org_lines=["Xứ đoàn A", "Giáo xứ B"],
                         logo_png=branding.logo_png(), summary=reports.summarize(df),
                         tables=[("Theo lớp", reports.pretty(by_class)), ("Sổ", matrix)])
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


def test_exports_neutralize_formulas():
    df = pd.DataFrame({"Họ và tên": ["=HYPERLINK(\"http://x\")", "+1+1", "@SUM(A1)", "-cmd", "Nguyễn An"],
                       "Mã": ["0001", "0002", "0003", "-12", "0005"]})
    out = reports.safe_cells(df)
    assert out["Họ và tên"].tolist()[:4] == ["'=HYPERLINK(\"http://x\")", "'+1+1", "'@SUM(A1)", "'-cmd"]
    assert out["Họ và tên"].iloc[4] == "Nguyễn An" and out["Mã"].iloc[3] == "-12"
    assert b"'=HYPERLINK" in reports.to_csv(df)


def test_leader_reports_scoped(admin, leader, school):
    make_session(admin, school)
    df = reports.attendance_frame(school["year"].id, leader)
    assert set(df["class_id"]) == {school["c1"]}


def test_settings_and_logo_persist_across_restart(admin, database):
    branding.save_settings(admin, {"xudoan_name": "Xứ đoàn Đaminh Savio", "primary_color": "#123456"})
    img = Image.new("RGBA", (300, 200), (200, 30, 30, 255))
    processed = branding.process_logo(img, branding.LogoEdit(square=True))
    assert processed.width == processed.height
    branding.save_logo(admin, branding.LOGO_XUDOAN, processed)
    # "Khởi động lại": bỏ engine + cache, kết nối lại cùng file
    db.get_engine().dispose()
    branding.invalidate()
    db.configure(database)
    db.init_db()
    assert branding.get_settings()["xudoan_name"] == "Xứ đoàn Đaminh Savio"
    assert branding.has_custom_logo(branding.LOGO_XUDOAN)
    assert branding.get_logo().getpixel((branding.get_logo().width // 2, branding.get_logo().height // 2))[0] == 200
    branding.reset_logo(admin, branding.LOGO_XUDOAN)
    assert not branding.has_custom_logo(branding.LOGO_XUDOAN)
    with pytest.raises(ValueError):
        branding.save_settings(admin, {"primary_color": "red"})


def test_logo_upload_validation():
    with pytest.raises(ValueError):
        branding.load_upload(b"not an image")
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="GIF")
    with pytest.raises(ValueError):
        branding.load_upload(buf.getvalue())
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="WEBP")
    assert branding.load_upload(buf.getvalue()).mode == "RGBA"


def test_settings_require_admin(admin, leader):
    with pytest.raises(PermissionDenied):
        branding.save_settings(leader, {"xudoan_name": "x"})


def test_backup_restore_roundtrip(admin, school):
    sid = make_session(admin, school)
    _mark(admin, sid, [C.PRESENT] * 10)
    blob = backup.export_backup(admin)
    manifest = backup.read_manifest(blob)
    assert manifest["counts"]["students"] == 11
    # thay đổi sau sao lưu
    students.delete_student(admin, school["inactive"])
    assert students.find_by_code("0099") is None
    counts = backup.restore_backup(admin, blob)
    assert counts["students"] == 11
    assert students.find_by_code("0099") is not None
    assert attendance.session_counts(sid)[C.PRESENT] == 10
    assert users.authenticate("admin", "Admin12345").ok
    # sau khôi phục vẫn thêm mới được (PostgreSQL: sequence phải được đặt lại)
    from tntt.services.students import StudentInput

    new_id = students.save_student(admin, StudentInput(code="7777", full_name="Sau Khôi Phục"), school["year"].id, None)
    assert new_id > max(school["students"][school["c2"]])
    with pytest.raises(ValueError):
        backup.read_manifest(b"garbage")


def test_postgres_rls_enabled_on_all_tables(database):
    if not database.startswith("postgresql"):
        pytest.skip("Chỉ áp dụng PostgreSQL")
    from sqlalchemy import text

    from tntt.models import Base

    with db.get_engine().connect() as conn:
        rows = dict(conn.execute(text(
            "SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace "
            "AND relkind = 'r'")).all())
    for table in Base.metadata.tables:
        assert rows.get(table) is True, f"RLS chưa bật cho bảng {table}"


def test_year_and_class_management(admin, school):
    with pytest.raises(ValueError):
        org.save_class(admin, school["year"].id, "Ấu Nhi 1", None)  # trùng tên trong năm
    with pytest.raises(ValueError):
        org.delete_class(admin, school["c1"])  # còn thiếu nhi
    with pytest.raises(ValueError):
        org.save_year(admin, "X", date(2030, 1, 1), date(2029, 1, 1), None, False)
