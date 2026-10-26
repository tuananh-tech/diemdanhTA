"""Năm học, ngành, lớp và phạm vi dữ liệu theo người dùng."""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import func, select, update

from ..db import session_scope
from ..models import AttendanceSession, Branch, ClassGroup, Enrollment, SchoolYear
from ..security import P_CLASSES, Actor, PermissionDenied
from . import audit


# ---- Năm học ---------------------------------------------------------------
def list_years() -> list[SchoolYear]:
    with session_scope() as s:
        return list(s.scalars(select(SchoolYear).order_by(SchoolYear.start_date.desc())).all())


def current_year() -> SchoolYear | None:
    with session_scope() as s:
        year = s.scalar(select(SchoolYear).where(SchoolYear.is_current.is_(True)))
        if year is None:
            year = s.scalar(select(SchoolYear).order_by(SchoolYear.start_date.desc()))
        return year


def get_year(year_id: int) -> SchoolYear | None:
    with session_scope() as s:
        return s.get(SchoolYear, year_id)


def save_year(actor: Actor, name: str, start: date, end: date, semester2_start: date | None,
              make_current: bool, year_id: int | None = None) -> int:
    actor.require(P_CLASSES)
    name = name.strip()
    if not name:
        raise ValueError("Cần nhập tên năm học, ví dụ 2025-2026.")
    if end <= start:
        raise ValueError("Ngày kết thúc phải sau ngày bắt đầu.")
    if semester2_start and not (start < semester2_start <= end):
        raise ValueError("Ngày bắt đầu học kỳ II phải nằm trong năm học.")
    with session_scope() as s:
        dup = s.scalar(select(SchoolYear.id).where(SchoolYear.name == name, SchoolYear.id != (year_id or 0)))
        if dup:
            raise ValueError("Tên năm học đã tồn tại.")
        year = s.get(SchoolYear, year_id) if year_id else SchoolYear(name=name, start_date=start, end_date=end)
        year.name, year.start_date, year.end_date, year.semester2_start = name, start, end, semester2_start
        if year_id is None:
            s.add(year)
        s.flush()
        if make_current:
            s.execute(update(SchoolYear).values(is_current=False))
            year.is_current = True
        audit.record(s, actor, "year.save", "school_year", year.id, name=name, current=make_current)
        return year.id


# ---- Ngành ---------------------------------------------------------------
def list_branches() -> list[Branch]:
    with session_scope() as s:
        return list(s.scalars(select(Branch).order_by(Branch.sort_order, Branch.name)).all())


def save_branch(actor: Actor, name: str, color: str, sort_order: int, branch_id: int | None = None) -> int:
    actor.require(P_CLASSES)
    name = name.strip()
    if not name:
        raise ValueError("Cần nhập tên ngành.")
    with session_scope() as s:
        if s.scalar(select(Branch.id).where(Branch.name == name, Branch.id != (branch_id or 0))):
            raise ValueError("Tên ngành đã tồn tại.")
        branch = s.get(Branch, branch_id) if branch_id else Branch(name=name)
        branch.name, branch.color, branch.sort_order = name, color, sort_order
        if branch_id is None:
            s.add(branch)
        s.flush()
        audit.record(s, actor, "branch.save", "branch", branch.id, name=name)
        return branch.id


def delete_branch(actor: Actor, branch_id: int) -> None:
    actor.require(P_CLASSES)
    with session_scope() as s:
        used = s.scalar(select(func.count(ClassGroup.id)).where(ClassGroup.branch_id == branch_id))
        if used:
            raise ValueError("Ngành đang có lớp, không thể xóa. Hãy chuyển các lớp sang ngành khác trước.")
        branch = s.get(Branch, branch_id)
        if branch:
            s.delete(branch)
            audit.record(s, actor, "branch.delete", "branch", branch_id, name=branch.name)


# ---- Lớp -------------------------------------------------------------------
def classes_frame(year_id: int, actor: Actor | None = None) -> pd.DataFrame:
    allowed = allowed_class_ids(actor, year_id) if actor else None
    with session_scope() as s:
        stmt = (
            select(ClassGroup.id, ClassGroup.name, ClassGroup.branch_id, Branch.name.label("branch"),
                   ClassGroup.sort_order, ClassGroup.note,
                   func.count(Enrollment.id).label("students"))
            .select_from(ClassGroup)
            .join(Branch, Branch.id == ClassGroup.branch_id, isouter=True)
            .join(Enrollment, Enrollment.class_id == ClassGroup.id, isouter=True)
            .where(ClassGroup.school_year_id == year_id)
            .group_by(ClassGroup.id, ClassGroup.name, ClassGroup.branch_id, Branch.name,
                      ClassGroup.sort_order, ClassGroup.note, Branch.sort_order)
            .order_by(Branch.sort_order, ClassGroup.sort_order, ClassGroup.name)
        )
        rows = s.execute(stmt).all()
    df = pd.DataFrame(rows, columns=["id", "name", "branch_id", "branch", "sort_order", "note", "students"])
    if allowed is not None:
        df = df[df["id"].isin(allowed)]
    return df.reset_index(drop=True)


def class_options(year_id: int, actor: Actor | None = None) -> dict[int, str]:
    df = classes_frame(year_id, actor)
    return {int(r.id): (f"{r.name} · {r.branch}" if r.branch else r.name) for r in df.itertuples()}


def get_or_create_class(s, year_id: int, name: str, branch_id: int | None) -> ClassGroup:
    name = name.strip()
    cls = s.scalar(select(ClassGroup).where(ClassGroup.school_year_id == year_id, ClassGroup.name == name))
    if cls is None:
        cls = ClassGroup(school_year_id=year_id, name=name, branch_id=branch_id)
        s.add(cls)
        s.flush()
    elif cls.branch_id is None and branch_id:
        cls.branch_id = branch_id
    return cls


def save_class(actor: Actor, year_id: int, name: str, branch_id: int | None, sort_order: int = 0,
               note: str | None = None, class_id: int | None = None) -> int:
    actor.require(P_CLASSES)
    name = name.strip()
    if not name:
        raise ValueError("Cần nhập tên lớp.")
    with session_scope() as s:
        dup = s.scalar(select(ClassGroup.id).where(
            ClassGroup.school_year_id == year_id, ClassGroup.name == name, ClassGroup.id != (class_id or 0)))
        if dup:
            raise ValueError("Năm học này đã có lớp cùng tên.")
        cls = s.get(ClassGroup, class_id) if class_id else ClassGroup(school_year_id=year_id, name=name)
        cls.name, cls.branch_id, cls.sort_order, cls.note = name, branch_id, sort_order, note
        if class_id is None:
            s.add(cls)
        s.flush()
        audit.record(s, actor, "class.save", "class", cls.id, name=name)
        return cls.id


def delete_class(actor: Actor, class_id: int) -> None:
    actor.require(P_CLASSES)
    with session_scope() as s:
        if s.scalar(select(func.count(Enrollment.id)).where(Enrollment.class_id == class_id)):
            raise ValueError("Lớp còn thiếu nhi. Hãy chuyển các em sang lớp khác trước khi xóa.")
        cls = s.get(ClassGroup, class_id)
        if cls:
            s.delete(cls)
            audit.record(s, actor, "class.delete", "class", class_id, name=cls.name)


# ---- Phạm vi dữ liệu ------------------------------------------------------
def allowed_class_ids(actor: Actor | None, year_id: int | None) -> set[int] | None:
    """None = không giới hạn. Tập rỗng = không được xem lớp nào."""
    if actor is None or actor.is_global:
        return None
    ids = set(actor.class_ids)
    if actor.branch_ids:
        with session_scope() as s:
            stmt = select(ClassGroup.id).where(ClassGroup.branch_id.in_(actor.branch_ids))
            if year_id:
                stmt = stmt.where(ClassGroup.school_year_id == year_id)
            ids |= set(s.scalars(stmt).all())
    return ids


def ensure_class_access(actor: Actor, year_id: int, class_ids) -> None:
    allowed = allowed_class_ids(actor, year_id)
    if allowed is None:
        return
    missing = {c for c in class_ids if c is not None} - allowed
    if missing or any(c is None for c in class_ids):
        raise PermissionDenied("Thao tác vượt ngoài các lớp/ngành bạn được phân công.")


def year_has_sessions(year_id: int) -> bool:
    with session_scope() as s:
        return bool(s.scalar(select(func.count(AttendanceSession.id)).where(AttendanceSession.school_year_id == year_id)))
