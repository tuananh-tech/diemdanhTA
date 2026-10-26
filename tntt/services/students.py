"""Hồ sơ thiếu nhi và ghi danh theo năm học."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import and_, func, or_, select

from .. import constants as C
from ..db import session_scope
from ..models import (
    AttendanceRecord,
    Branch,
    ClassGroup,
    Enrollment,
    QrCredential,
    Student,
)
from ..security import P_STUDENTS_EDIT, P_STUDENTS_VIEW, P_USERS, Actor, PermissionDenied
from ..textutil import clean_name, normalize_code, search_key
from . import audit, org

STUDENT_COLUMNS = [
    "id", "code", "saint_name", "full_name", "birth_date", "gender", "parent_name", "parent_phone",
    "note", "status", "enrollment_id", "class_id", "class_name", "branch_id", "branch", "team", "qr_active",
]


@dataclass
class StudentInput:
    code: str
    full_name: str
    saint_name: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    parent_name: str | None = None
    parent_phone: str | None = None
    note: str | None = None
    status: str = "active"

    def normalized(self) -> "StudentInput":
        gender = (self.gender or "").strip().upper()[:1] or None
        if gender not in (None, "M", "F"):
            gender = None
        status = self.status if self.status in C.STUDENT_STATUS_LABELS else "active"
        phone = re.sub(r"[^\d+]", "", self.parent_phone or "") or None
        return StudentInput(
            code=normalize_code(self.code),
            full_name=clean_name(self.full_name),
            saint_name=clean_name(self.saint_name) or None,
            birth_date=self.birth_date,
            gender=gender,
            parent_name=clean_name(self.parent_name) or None,
            parent_phone=phone,
            note=clean_name(self.note) or None,
            status=status,
        )


def _apply(student: Student, data: StudentInput) -> None:
    student.code = data.code
    student.full_name = data.full_name
    student.saint_name = data.saint_name
    student.birth_date = data.birth_date
    student.gender = data.gender
    student.parent_name = data.parent_name
    student.parent_phone = data.parent_phone
    student.note = data.note
    student.status = data.status
    student.search_text = search_key(data.code, data.saint_name, data.full_name)


def display_name(saint_name: str | None, full_name: str) -> str:
    return f"{saint_name} {full_name}".strip() if saint_name else full_name


# ---- Truy vấn ----------------------------------------------------------------
def students_frame(year_id: int, actor: Actor | None = None, *, branch_id: int | None = None,
                   class_id: int | None = None, status: str | None = None, search: str | None = None,
                   include_unenrolled: bool = True) -> pd.DataFrame:
    if actor is not None:
        actor.require(P_STUDENTS_VIEW)
    allowed = org.allowed_class_ids(actor, year_id)
    with session_scope() as s:
        qr_active = select(QrCredential.student_id).where(QrCredential.status == "active")
        stmt = (
            select(
                Student.id, Student.code, Student.saint_name, Student.full_name, Student.birth_date,
                Student.gender, Student.parent_name, Student.parent_phone, Student.note, Student.status,
                Enrollment.id, Enrollment.class_id, ClassGroup.name, ClassGroup.branch_id, Branch.name,
                Enrollment.team, Student.id.in_(qr_active),
            )
            .select_from(Student)
            .join(Enrollment, and_(Enrollment.student_id == Student.id, Enrollment.school_year_id == year_id),
                  isouter=True)
            .join(ClassGroup, ClassGroup.id == Enrollment.class_id, isouter=True)
            .join(Branch, Branch.id == ClassGroup.branch_id, isouter=True)
        )
        if allowed is not None:
            stmt = stmt.where(Enrollment.class_id.in_(allowed or {-1}))
        elif not include_unenrolled:
            stmt = stmt.where(Enrollment.id.is_not(None))
        if class_id:
            stmt = stmt.where(Enrollment.class_id == class_id)
        if branch_id:
            stmt = stmt.where(ClassGroup.branch_id == branch_id)
        if status:
            stmt = stmt.where(Student.status == status)
        if search and search.strip():
            key = search_key(search)
            stmt = stmt.where(or_(Student.search_text.like(f"%{key}%"),
                                  Student.code == normalize_code(search)))
        stmt = stmt.order_by(Branch.sort_order, ClassGroup.name, Student.full_name)
        rows = s.execute(stmt).all()
    df = pd.DataFrame(rows, columns=STUDENT_COLUMNS)
    if not df.empty:
        # Sắp xếp theo TÊN (từ cuối) như thói quen Việt Nam
        df["_sort"] = df["full_name"].map(lambda n: search_key(n.split(" ")[-1] if n else "") + " " + search_key(n))
        df = df.sort_values(["branch", "class_name", "_sort"], na_position="last").drop(columns="_sort")
    return df.reset_index(drop=True)


def get_student(student_id: int) -> Student | None:
    with session_scope() as s:
        return s.get(Student, student_id)


def find_by_code(code: str) -> Student | None:
    with session_scope() as s:
        return s.scalar(select(Student).where(Student.code == normalize_code(code)))


def get_enrollment(student_id: int, year_id: int) -> Enrollment | None:
    with session_scope() as s:
        return s.scalar(select(Enrollment).where(Enrollment.student_id == student_id,
                                                 Enrollment.school_year_id == year_id))


def enrollment_history(student_id: int) -> pd.DataFrame:
    from ..models import SchoolYear

    with session_scope() as s:
        rows = s.execute(
            select(SchoolYear.name, ClassGroup.name, Branch.name, Enrollment.team)
            .select_from(Enrollment)
            .join(SchoolYear, SchoolYear.id == Enrollment.school_year_id)
            .join(ClassGroup, ClassGroup.id == Enrollment.class_id, isouter=True)
            .join(Branch, Branch.id == ClassGroup.branch_id, isouter=True)
            .where(Enrollment.student_id == student_id)
            .order_by(SchoolYear.start_date.desc())
        ).all()
    return pd.DataFrame(rows, columns=["Năm học", "Lớp", "Ngành", "Đội"])


def next_code(prefix: str = "TN", width: int = 4) -> str:
    """Mã kế tiếp. Nếu dữ liệu hiện có toàn số -> tăng số (giữ độ dài, số 0 ở đầu)."""
    with session_scope() as s:
        codes = s.scalars(select(Student.code)).all()
    numeric = [c for c in codes if c.isdigit()]
    if codes and len(numeric) == len(codes):
        w = max(len(c) for c in numeric)
        return str(max(int(c) for c in numeric) + 1).zfill(w)
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    nums = [int(m.group(1)) for c in codes if (m := pattern.match(c))]
    return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"


# ---- Ghi --------------------------------------------------------------------
def validate_input(data: StudentInput) -> list[str]:
    errors = []
    if not data.code:
        errors.append("Thiếu mã thiếu nhi.")
    elif not re.fullmatch(r"[A-Z0-9._-]{1,32}", data.code):
        errors.append("Mã chỉ gồm chữ, số, dấu . _ - (tối đa 32 ký tự).")
    if not data.full_name:
        errors.append("Thiếu họ và tên.")
    if data.birth_date and not (date(1950, 1, 1) <= data.birth_date <= date.today()):
        errors.append("Ngày sinh không hợp lệ.")
    return errors


def _check_edit_scope(s, actor: Actor, year_id: int, student_id: int | None, class_id: int | None) -> None:
    actor.require(P_STUDENTS_EDIT)
    if actor.is_global:
        return
    targets = [class_id]
    if student_id:
        current = s.scalar(select(Enrollment.class_id).where(Enrollment.student_id == student_id,
                                                             Enrollment.school_year_id == year_id))
        targets.append(current)
    org.ensure_class_access(actor, year_id, targets)


def set_enrollment(s, student_id: int, year_id: int, class_id: int | None, team: str | None) -> Enrollment:
    enr = s.scalar(select(Enrollment).where(Enrollment.student_id == student_id,
                                            Enrollment.school_year_id == year_id))
    if enr is None:
        enr = Enrollment(student_id=student_id, school_year_id=year_id)
        s.add(enr)
    enr.class_id = class_id
    enr.team = clean_name(team) or None
    return enr


def save_student(actor: Actor, data: StudentInput, year_id: int, class_id: int | None,
                 team: str | None = None, student_id: int | None = None) -> int:
    data = data.normalized()
    errors = validate_input(data)
    if errors:
        raise ValueError(" ".join(errors))
    with session_scope() as s:
        _check_edit_scope(s, actor, year_id, student_id, class_id)
        dup = s.scalar(select(Student.id).where(Student.code == data.code, Student.id != (student_id or 0)))
        if dup:
            raise ValueError(f"Mã {data.code} đã được dùng cho thiếu nhi khác.")
        if student_id:
            student = s.get(Student, student_id)
            if student is None:
                raise ValueError("Không tìm thấy thiếu nhi.")
        else:
            student = Student(code=data.code, full_name=data.full_name)
            s.add(student)
        _apply(student, data)
        s.flush()
        set_enrollment(s, student.id, year_id, class_id, team)
        audit.record(s, actor, "student.update" if student_id else "student.create", "student", student.id,
                     code=data.code, class_id=class_id)
        return student.id


def transfer_students(actor: Actor, student_ids: list[int], year_id: int, to_class_id: int | None) -> int:
    """Chuyển lớp trong năm học. Các phiên đã lập danh sách giữ nguyên lớp cũ (lịch sử)."""
    with session_scope() as s:
        count = 0
        for sid in student_ids:
            _check_edit_scope(s, actor, year_id, sid, to_class_id)
            enr = s.scalar(select(Enrollment).where(Enrollment.student_id == sid, Enrollment.school_year_id == year_id))
            set_enrollment(s, sid, year_id, to_class_id, enr.team if enr else None)
            count += 1
        audit.record(s, actor, "student.transfer", "class", to_class_id, student_ids=student_ids, year_id=year_id)
        return count


def promote_year(actor: Actor, from_year_id: int, to_year_id: int, class_map: dict[int, int | None],
                 only_active: bool = True, keep_team: bool = True) -> dict:
    """Chuyển năm học: tạo ghi danh mới ở năm đích theo bảng ánh xạ lớp.
    Ghi danh năm cũ được giữ nguyên. Em đã có ghi danh ở năm đích thì bỏ qua."""
    if not actor.is_global:
        raise PermissionDenied("Chỉ Ban Điều hành/Quản trị được chuyển năm học.")
    if from_year_id == to_year_id:
        raise ValueError("Năm nguồn và năm đích phải khác nhau.")
    result = {"created": 0, "skipped_existing": 0, "skipped_unmapped": 0, "skipped_inactive": 0}
    with session_scope() as s:
        existing = set(s.scalars(select(Enrollment.student_id).where(Enrollment.school_year_id == to_year_id)).all())
        rows = s.execute(
            select(Enrollment.student_id, Enrollment.class_id, Enrollment.team, Student.status)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.school_year_id == from_year_id)
        ).all()
        for sid, cid, team, status in rows:
            if sid in existing:
                result["skipped_existing"] += 1
                continue
            if only_active and status != "active":
                result["skipped_inactive"] += 1
                continue
            target = class_map.get(cid)
            if target is None:
                result["skipped_unmapped"] += 1
                continue
            s.add(Enrollment(student_id=sid, school_year_id=to_year_id, class_id=target,
                             team=team if keep_team else None))
            result["created"] += 1
        audit.record(s, actor, "student.promote_year", "school_year", to_year_id,
                     from_year_id=from_year_id, **result)
    return result


def set_status(actor: Actor, student_ids: list[int], status: str, year_id: int) -> None:
    if status not in C.STUDENT_STATUS_LABELS:
        raise ValueError("Tình trạng không hợp lệ.")
    with session_scope() as s:
        for sid in student_ids:
            current_class = s.scalar(select(Enrollment.class_id).where(
                Enrollment.student_id == sid, Enrollment.school_year_id == year_id))
            _check_edit_scope(s, actor, year_id, sid, current_class)
            st = s.get(Student, sid)
            if st:
                st.status = status
        audit.record(s, actor, "student.set_status", "student", None, student_ids=student_ids, status=status)


def delete_student(actor: Actor, student_id: int) -> None:
    """Xóa hẳn chỉ khi chưa có dữ liệu điểm danh. Nếu đã có -> đổi tình trạng."""
    actor.require(P_USERS)
    with session_scope() as s:
        n = s.scalar(select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.student_id == student_id, AttendanceRecord.status != C.UNMARKED))
        if n:
            raise ValueError("Thiếu nhi đã có lịch sử điểm danh. Hãy đổi tình trạng thành 'Tạm nghỉ'/'Chuyển xứ' thay vì xóa.")
        st = s.get(Student, student_id)
        if st:
            audit.record(s, actor, "student.delete", "student", student_id, code=st.code)
            s.delete(st)
