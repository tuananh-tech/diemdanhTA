"""Phiên điểm danh: tạo (đơn lẻ / theo lịch), mở, đồng bộ danh sách, đóng.

Khi MỞ phiên, hệ thống lập danh sách (roster) = các thiếu nhi đang sinh hoạt,
ghi danh vào lớp thuộc phạm vi phiên. Mỗi em có đúng một bản ghi trạng thái
'Chưa điểm danh'. Em chưa được quét KHÔNG bị coi là vắng cho tới khi người phụ
trách chủ động chốt phiên.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta

import pandas as pd
from sqlalchemy import case, delete, func, select

from .. import constants as C
from ..db import session_scope
from ..models import (
    AttendanceLog,
    AttendanceRecord,
    AttendanceSession,
    ClassGroup,
    Enrollment,
    SessionClass,
    Student,
    User,
    utcnow,
)
from ..security import P_ATTEND_CLOSED, P_SESSIONS, Actor, PermissionDenied
from . import audit, org


def _new_uid() -> str:
    return secrets.token_hex(8)


# ---- Truy vấn ----------------------------------------------------------------
def get_session(session_id: int) -> AttendanceSession | None:
    with session_scope() as s:
        return s.get(AttendanceSession, session_id)


def session_class_ids(session_id: int) -> set[int]:
    with session_scope() as s:
        return set(s.scalars(select(SessionClass.class_id).where(SessionClass.session_id == session_id)).all())


def actor_classes_in_session(actor: Actor, sess: AttendanceSession) -> set[int] | None:
    """Các lớp trong phiên mà người dùng được thao tác. None = tất cả."""
    allowed = org.allowed_class_ids(actor, sess.school_year_id)
    if allowed is None:
        return None
    if sess.scope_all:
        return allowed
    return allowed & session_class_ids(sess.id)


def can_view_session(actor: Actor, sess: AttendanceSession) -> bool:
    scope = actor_classes_in_session(actor, sess)
    return scope is None or bool(scope)


def list_sessions(year_id: int, actor: Actor | None = None, date_from: date | None = None,
                  date_to: date | None = None, status: str | None = None) -> pd.DataFrame:
    with session_scope() as s:
        counts = (
            select(
                AttendanceRecord.session_id.label("sid"),
                func.count(AttendanceRecord.id).label("eligible"),
                func.sum(case((AttendanceRecord.status != C.UNMARKED, 1), else_=0)).label("marked"),
                func.sum(case((AttendanceRecord.status.in_(C.ATTENDED_STATUSES), 1), else_=0)).label("attended"),
            ).group_by(AttendanceRecord.session_id).subquery()
        )
        stmt = (
            select(AttendanceSession.id, AttendanceSession.uid, AttendanceSession.title,
                   AttendanceSession.activity_type, AttendanceSession.session_date, AttendanceSession.start_time,
                   AttendanceSession.late_after, AttendanceSession.status, AttendanceSession.scope_all,
                   User.full_name.label("owner"), counts.c.eligible, counts.c.marked, counts.c.attended)
            .select_from(AttendanceSession)
            .join(User, User.id == AttendanceSession.owner_id, isouter=True)
            .join(counts, counts.c.sid == AttendanceSession.id, isouter=True)
            .where(AttendanceSession.school_year_id == year_id)
            .order_by(AttendanceSession.session_date.desc(), AttendanceSession.start_time.desc())
        )
        if date_from:
            stmt = stmt.where(AttendanceSession.session_date >= date_from)
        if date_to:
            stmt = stmt.where(AttendanceSession.session_date <= date_to)
        if status:
            stmt = stmt.where(AttendanceSession.status == status)
        rows = s.execute(stmt).all()
        links = s.execute(
            select(SessionClass.session_id, ClassGroup.id, ClassGroup.name)
            .join(ClassGroup, ClassGroup.id == SessionClass.class_id)
            .where(ClassGroup.school_year_id == year_id)
        ).all()
    df = pd.DataFrame(rows, columns=["id", "uid", "title", "activity_type", "session_date", "start_time",
                                     "late_after", "status", "scope_all", "owner", "eligible", "marked", "attended"])
    class_map: dict[int, list[tuple[int, str]]] = {}
    for sid, cid, name in links:
        class_map.setdefault(sid, []).append((cid, name))
    df["class_ids"] = df["id"].map(lambda i: [c for c, _ in class_map.get(i, [])])
    df["classes"] = [
        "Toàn Xứ đoàn" if all_ else ", ".join(sorted(n for _, n in class_map.get(i, [])))
        for i, all_ in zip(df["id"], df["scope_all"])
    ]
    for col in ("eligible", "marked", "attended"):
        df[col] = df[col].fillna(0).astype(int)
    allowed = org.allowed_class_ids(actor, year_id) if actor else None
    if allowed is not None:
        df = df[df["scope_all"] | df["class_ids"].map(lambda ids: bool(set(ids) & allowed))]
    return df.reset_index(drop=True)


# ---- Tạo phiên ----------------------------------------------------------------
def _check_manage(actor: Actor, year_id: int, class_ids: list[int], scope_all: bool) -> None:
    actor.require(P_SESSIONS)
    if actor.is_global:
        return
    if scope_all:
        raise PermissionDenied("Chỉ Ban Điều hành được tạo phiên cho toàn Xứ đoàn.")
    if not class_ids:
        raise ValueError("Hãy chọn ít nhất một lớp.")
    org.ensure_class_access(actor, year_id, class_ids)


def create_session(actor: Actor, *, year_id: int, title: str, activity_type: str, session_date: date,
                   start_time: time | None, late_after: time | None, class_ids: list[int],
                   scope_all: bool = False, owner_id: int | None = None, note: str | None = None,
                   open_now: bool = True) -> int:
    title = (title or "").strip() or activity_type
    if not scope_all and not class_ids:
        raise ValueError("Hãy chọn lớp tham dự hoặc chọn 'Toàn Xứ đoàn'.")
    if start_time and late_after and late_after < start_time:
        raise ValueError("Mốc tính đi trễ phải sau giờ bắt đầu.")
    _check_manage(actor, year_id, class_ids, scope_all)
    with session_scope() as s:
        sess = AttendanceSession(
            uid=_new_uid(), school_year_id=year_id, title=title[:150], activity_type=activity_type,
            session_date=session_date, start_time=start_time, late_after=late_after,
            status=C.SESSION_SCHEDULED, scope_all=scope_all, owner_id=owner_id or actor.id,
            note=note, created_by=actor.id,
        )
        s.add(sess)
        s.flush()
        for cid in set(class_ids if not scope_all else []):
            s.add(SessionClass(session_id=sess.id, class_id=cid))
        s.flush()
        audit.record(s, actor, "session.create", "session", sess.id, title=title, date=session_date,
                     class_ids=sorted(set(class_ids)), scope_all=scope_all)
        if open_now:
            _open(s, actor, sess)
        return sess.id


def create_recurring(actor: Actor, *, year_id: int, start: date, end: date, weekdays: list[int],
                     activity_type: str, start_time: time | None, late_minutes: int | None,
                     class_ids: list[int], scope_all: bool = False, title_prefix: str | None = None) -> dict:
    """Tạo nhiều phiên theo lịch (ví dụ mọi Chủ nhật). Bỏ qua phiên đã tồn tại."""
    if end < start:
        raise ValueError("Ngày kết thúc phải sau ngày bắt đầu.")
    if (end - start).days > 400:
        raise ValueError("Khoảng thời gian tối đa 400 ngày.")
    if not weekdays:
        raise ValueError("Hãy chọn ít nhất một thứ trong tuần.")
    _check_manage(actor, year_id, class_ids, scope_all)
    late_after = None
    if start_time and late_minutes is not None:
        late_after = (datetime.combine(date.today(), start_time) + timedelta(minutes=late_minutes)).time()
    created = skipped = 0
    with session_scope() as s:
        d = start
        while d <= end:
            if d.weekday() in weekdays:
                title = f"{title_prefix or activity_type} {d:%d/%m/%Y}"
                exists = s.scalar(select(AttendanceSession.id).where(
                    AttendanceSession.school_year_id == year_id, AttendanceSession.session_date == d,
                    AttendanceSession.activity_type == activity_type, AttendanceSession.title == title))
                if exists:
                    skipped += 1
                else:
                    sess = AttendanceSession(uid=_new_uid(), school_year_id=year_id, title=title,
                                             activity_type=activity_type, session_date=d, start_time=start_time,
                                             late_after=late_after, status=C.SESSION_SCHEDULED,
                                             scope_all=scope_all, owner_id=actor.id, created_by=actor.id)
                    s.add(sess)
                    s.flush()
                    for cid in set(class_ids if not scope_all else []):
                        s.add(SessionClass(session_id=sess.id, class_id=cid))
                    created += 1
            d += timedelta(days=1)
        audit.record(s, actor, "session.create_recurring", "school_year", year_id, created=created,
                     skipped=skipped, activity_type=activity_type, start=start, end=end)
    return {"created": created, "skipped": skipped}


def update_session(actor: Actor, session_id: int, *, title: str, activity_type: str, session_date: date,
                   start_time: time | None, late_after: time | None, owner_id: int | None,
                   note: str | None) -> None:
    with session_scope() as s:
        sess = _get_for_manage(s, actor, session_id)
        sess.title, sess.activity_type, sess.session_date = title.strip() or sess.title, activity_type, session_date
        sess.start_time, sess.late_after, sess.owner_id, sess.note = start_time, late_after, owner_id, note
        audit.record(s, actor, "session.update", "session", session_id, title=sess.title)


def _get_for_manage(s, actor: Actor, session_id: int) -> AttendanceSession:
    sess = s.get(AttendanceSession, session_id)
    if sess is None:
        raise ValueError("Không tìm thấy phiên.")
    class_ids = list(s.scalars(select(SessionClass.class_id).where(SessionClass.session_id == session_id)).all())
    _check_manage(actor, sess.school_year_id, class_ids, sess.scope_all)
    return sess


# ---- Danh sách tham dự (roster) ---------------------------------------------
def _eligible(s, sess: AttendanceSession) -> dict[int, int | None]:
    """student_id -> class_id của các em thuộc đối tượng tham dự phiên."""
    stmt = (
        select(Enrollment.student_id, Enrollment.class_id)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.school_year_id == sess.school_year_id, Student.status == "active")
    )
    if not sess.scope_all:
        stmt = stmt.where(Enrollment.class_id.in_(
            select(SessionClass.class_id).where(SessionClass.session_id == sess.id)))
    return dict(s.execute(stmt).all())


def _sync(s, sess: AttendanceSession) -> dict[str, int]:
    eligible = _eligible(s, sess)
    existing = {sid: (rid, status) for rid, sid, status in s.execute(
        select(AttendanceRecord.id, AttendanceRecord.student_id, AttendanceRecord.status)
        .where(AttendanceRecord.session_id == sess.id)).all()}
    added = removed = 0
    for sid, cid in eligible.items():
        if sid not in existing:
            s.add(AttendanceRecord(session_id=sess.id, student_id=sid, class_id=cid, status=C.UNMARKED))
            added += 1
    # Chỉ gỡ những em CHƯA được điểm danh và không còn thuộc đối tượng.
    stale = [rid for sid, (rid, status) in existing.items() if sid not in eligible and status == C.UNMARKED]
    if stale:
        s.execute(delete(AttendanceRecord).where(AttendanceRecord.id.in_(stale)))
        removed = len(stale)
    s.flush()
    return {"added": added, "removed": removed}


def _open(s, actor: Actor, sess: AttendanceSession) -> dict[str, int]:
    result = _sync(s, sess)
    sess.status = C.SESSION_OPEN
    sess.opened_at = sess.opened_at or utcnow()
    audit.record(s, actor, "session.open", "session", sess.id, **result)
    return result


def open_session(actor: Actor, session_id: int) -> dict[str, int]:
    with session_scope() as s:
        sess = _get_for_manage(s, actor, session_id)
        if sess.status == C.SESSION_CLOSED:
            actor.require(P_ATTEND_CLOSED)
        return _open(s, actor, sess)


def sync_roster(actor: Actor, session_id: int) -> dict[str, int]:
    with session_scope() as s:
        sess = _get_for_manage(s, actor, session_id)
        if sess.status != C.SESSION_OPEN:
            raise ValueError("Chỉ đồng bộ danh sách khi phiên đang mở.")
        result = _sync(s, sess)
        audit.record(s, actor, "session.sync_roster", "session", session_id, **result)
        return result


def close_session(actor: Actor, session_id: int, mark_unmarked_as: str | None = None) -> int:
    """Đóng phiên. Tùy chọn: chuyển các em 'Chưa điểm danh' sang trạng thái chỉ định."""
    if mark_unmarked_as not in (None, C.ABSENT, C.EXCUSED):
        raise ValueError("Trạng thái chốt không hợp lệ.")
    with session_scope() as s:
        sess = _get_for_manage(s, actor, session_id)
        changed = 0
        if mark_unmarked_as:
            records = s.scalars(select(AttendanceRecord).where(
                AttendanceRecord.session_id == session_id, AttendanceRecord.status == C.UNMARKED)).all()
            now = utcnow()
            for r in records:
                s.add(AttendanceLog(record_id=r.id, session_id=session_id, student_id=r.student_id,
                                    old_status=C.UNMARKED, new_status=mark_unmarked_as, method=C.METHOD_SYSTEM,
                                    user_id=actor.id, note="Chốt khi đóng phiên", at=now))
                r.status, r.method, r.marked_by, r.marked_at = mark_unmarked_as, C.METHOD_SYSTEM, actor.id, now
                r.version += 1
                changed += 1
        sess.status = C.SESSION_CLOSED
        sess.closed_at = utcnow()
        sess.closed_by = actor.id
        audit.record(s, actor, "session.close", "session", session_id, finalized=changed,
                     mark_unmarked_as=mark_unmarked_as)
        return changed


def reopen_session(actor: Actor, session_id: int) -> None:
    actor.require(P_ATTEND_CLOSED)
    with session_scope() as s:
        sess = _get_for_manage(s, actor, session_id)
        sess.status = C.SESSION_OPEN
        sess.closed_at = None
        audit.record(s, actor, "session.reopen", "session", session_id)


def delete_session(actor: Actor, session_id: int) -> None:
    with session_scope() as s:
        sess = _get_for_manage(s, actor, session_id)
        marked = s.scalar(select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.session_id == session_id, AttendanceRecord.status != C.UNMARKED))
        if marked and not actor.can(P_ATTEND_CLOSED):
            raise PermissionDenied("Phiên đã có dữ liệu điểm danh. Chỉ Ban Điều hành được xóa.")
        audit.record(s, actor, "session.delete", "session", session_id, title=sess.title, marked=marked)
        s.delete(sess)


def today_open_sessions(year_id: int, actor: Actor, today: date) -> pd.DataFrame:
    df = list_sessions(year_id, actor, date_from=today - timedelta(days=1), date_to=today + timedelta(days=1))
    return df[df["status"] == C.SESSION_OPEN].reset_index(drop=True)
