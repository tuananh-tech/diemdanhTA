"""Ghi nhận điểm danh (thủ công, QR, nhập mã, hàng loạt, khuôn mặt đã xác nhận).

An toàn đồng thời:
- UNIQUE(session_id, student_id) ở DB: mỗi em chỉ một bản ghi/phiên.
- Mọi thay đổi là UPDATE có điều kiện (WHERE version = ? hoặc WHERE status =
  'unmarked'), nguyên tử ở cả PostgreSQL và SQLite -> hai Huynh trưởng quét
  cùng lúc chỉ một người ghi nhận được, người kia nhận thông báo "đã điểm danh".
- Nhật ký thay đổi ghi trong CÙNG giao dịch. Lỗi CSDL -> rollback, không có
  bản ghi "nửa vời".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

from .. import config
from .. import constants as C
from ..db import session_scope
from ..models import (
    AttendanceLog,
    AttendanceRecord,
    AttendanceSession,
    ClassGroup,
    QrCredential,
    Student,
    User,
    utcnow,
)
from ..security import P_ATTEND, P_ATTEND_CLOSED, Actor, PermissionDenied
from ..textutil import normalize_code, search_key
from . import sessions as sessions_svc

log = logging.getLogger(__name__)


@dataclass
class MarkResult:
    ok: bool
    kind: str  # success | unchanged | duplicate | invalid | revoked | not_in_session | closed | conflict | denied | error
    message: str
    student: dict = field(default_factory=dict)
    status: str | None = None
    marked_at: datetime | None = None
    marked_by: str | None = None
    method: str | None = None
    version: int | None = None


def to_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    from datetime import timezone

    return dt.replace(tzinfo=timezone.utc).astimezone(config.LOCAL_TZ)


def now_local() -> datetime:
    return to_local(utcnow())


def status_for_arrival(sess: AttendanceSession, at_local: datetime | None = None) -> str:
    """Có mặt hay Đi trễ, dựa vào mốc tính trễ của phiên (chỉ áp dụng trong ngày phiên)."""
    at_local = at_local or now_local()
    if sess.late_after and at_local.date() == sess.session_date and at_local.time() > sess.late_after:
        return C.LATE
    return C.PRESENT


# ---- Truy vấn ------------------------------------------------------------------
def roster_frame(session_id: int, *, class_ids: set[int] | None = None, search: str | None = None,
                 only_unmarked: bool = False) -> pd.DataFrame:
    with session_scope() as s:
        stmt = (
            select(AttendanceRecord.id, AttendanceRecord.student_id, Student.code, Student.saint_name,
                   Student.full_name, AttendanceRecord.class_id, ClassGroup.name, AttendanceRecord.status,
                   AttendanceRecord.method, AttendanceRecord.note, AttendanceRecord.marked_at,
                   User.full_name, AttendanceRecord.version)
            .select_from(AttendanceRecord)
            .join(Student, Student.id == AttendanceRecord.student_id)
            .join(ClassGroup, ClassGroup.id == AttendanceRecord.class_id, isouter=True)
            .join(User, User.id == AttendanceRecord.marked_by, isouter=True)
            .where(AttendanceRecord.session_id == session_id)
        )
        if class_ids is not None:
            stmt = stmt.where(AttendanceRecord.class_id.in_(class_ids or {-1}))
        if only_unmarked:
            stmt = stmt.where(AttendanceRecord.status == C.UNMARKED)
        if search and search.strip():
            key = search_key(search)
            stmt = stmt.where(Student.search_text.like(f"%{key}%"))
        rows = s.execute(stmt).all()
    df = pd.DataFrame(rows, columns=["record_id", "student_id", "code", "saint_name", "full_name", "class_id",
                                     "class_name", "status", "method", "note", "marked_at", "marked_by",
                                     "version"])
    if not df.empty:
        df["_k"] = df["full_name"].map(lambda n: search_key(n.split(" ")[-1]) + " " + search_key(n))
        df = df.sort_values(["class_name", "_k"], na_position="last").drop(columns="_k")
    return df.reset_index(drop=True)


def session_counts(session_id: int, class_ids: set[int] | None = None) -> dict[str, int]:
    with session_scope() as s:
        stmt = (select(AttendanceRecord.status, func.count(AttendanceRecord.id))
                .where(AttendanceRecord.session_id == session_id).group_by(AttendanceRecord.status))
        if class_ids is not None:
            stmt = stmt.where(AttendanceRecord.class_id.in_(class_ids or {-1}))
        rows = dict(s.execute(stmt).all())
    counts = {st: int(rows.get(st, 0)) for st in C.STATUSES}
    counts["total"] = sum(counts[st] for st in C.STATUSES)
    return counts


def recent_activity(session_id: int, limit: int = 10, methods: tuple[str, ...] | None = None) -> pd.DataFrame:
    with session_scope() as s:
        stmt = (
            select(AttendanceLog.at, Student.code, Student.saint_name, Student.full_name, AttendanceLog.old_status,
                   AttendanceLog.new_status, AttendanceLog.method, User.full_name)
            .join(Student, Student.id == AttendanceLog.student_id)
            .join(User, User.id == AttendanceLog.user_id, isouter=True)
            .where(AttendanceLog.session_id == session_id)
            .order_by(AttendanceLog.at.desc(), AttendanceLog.id.desc())
            .limit(limit)
        )
        if methods:
            stmt = stmt.where(AttendanceLog.method.in_(methods))
        rows = s.execute(stmt).all()
    return pd.DataFrame(rows, columns=["at", "code", "saint_name", "full_name", "old_status", "new_status",
                                       "method", "by"])


def record_history(record_id: int) -> pd.DataFrame:
    with session_scope() as s:
        rows = s.execute(
            select(AttendanceLog.at, AttendanceLog.old_status, AttendanceLog.new_status, AttendanceLog.method,
                   AttendanceLog.note, User.full_name)
            .join(User, User.id == AttendanceLog.user_id, isouter=True)
            .where(AttendanceLog.record_id == record_id).order_by(AttendanceLog.at.desc())
        ).all()
    return pd.DataFrame(rows, columns=["at", "old_status", "new_status", "method", "note", "by"])


# ---- Ghi -------------------------------------------------------------------------
def _student_info(st: Student, class_name: str | None) -> dict:
    return {"id": st.id, "code": st.code, "saint_name": st.saint_name or "", "full_name": st.full_name,
            "class_name": class_name or ""}


def _marker_name(s, user_id: int | None) -> str | None:
    return s.scalar(select(User.full_name).where(User.id == user_id)) if user_id else None


def _check_session_writable(actor: Actor, sess: AttendanceSession) -> MarkResult | None:
    if sess.status == C.SESSION_SCHEDULED:
        return MarkResult(False, "closed", "Phiên chưa mở. Hãy mở phiên trước khi điểm danh.")
    if sess.status == C.SESSION_CLOSED and not actor.can(P_ATTEND_CLOSED):
        return MarkResult(False, "closed", "Phiên đã đóng. Chỉ Ban Điều hành được sửa.")
    return None


def set_status(actor: Actor, record_id: int, new_status: str, *, method: str = C.METHOD_MANUAL,
               note: str | None = None, expected_version: int | None = None) -> MarkResult:
    """Đổi trạng thái 1 bản ghi (thủ công). note=None nghĩa là giữ nguyên ghi chú."""
    if new_status not in C.STATUSES:
        return MarkResult(False, "invalid", "Trạng thái không hợp lệ.")
    try:
        actor.require(P_ATTEND)
        with session_scope() as s:
            rec = s.get(AttendanceRecord, record_id)
            if rec is None:
                return MarkResult(False, "invalid", "Không tìm thấy bản ghi điểm danh.")
            sess = s.get(AttendanceSession, rec.session_id)
            blocked = _check_session_writable(actor, sess)
            if blocked:
                return blocked
            scope = sessions_svc.actor_classes_in_session(actor, sess)
            if scope is not None and rec.class_id not in scope:
                return MarkResult(False, "denied", "Em này không thuộc lớp bạn phụ trách.")
            st = s.get(Student, rec.student_id)
            class_name = s.scalar(select(ClassGroup.name).where(ClassGroup.id == rec.class_id))
            info = _student_info(st, class_name)
            if expected_version is not None and rec.version != expected_version:
                return MarkResult(False, "conflict", "Dữ liệu vừa được người khác cập nhật. Đã tải lại trạng thái mới.",
                                  info, rec.status, rec.marked_at, _marker_name(s, rec.marked_by), rec.method,
                                  rec.version)
            new_note = rec.note if note is None else (note.strip()[:255] or None)
            if rec.status == new_status and new_note == rec.note:
                return MarkResult(True, "unchanged", "Không có thay đổi.", info, rec.status, rec.marked_at,
                                  _marker_name(s, rec.marked_by), rec.method, rec.version)
            now = utcnow()
            unmark = new_status == C.UNMARKED
            res = s.execute(
                update(AttendanceRecord)
                .where(AttendanceRecord.id == rec.id, AttendanceRecord.version == rec.version)
                .values(status=new_status, note=new_note,
                        method=None if unmark else method,
                        marked_by=None if unmark else actor.id,
                        marked_at=None if unmark else now,
                        version=AttendanceRecord.version + 1)
                .execution_options(synchronize_session=False)
            )
            if res.rowcount != 1:
                return MarkResult(False, "conflict", "Dữ liệu vừa được người khác cập nhật. Hãy thử lại.", info)
            if rec.status != new_status or new_note != rec.note:
                s.add(AttendanceLog(record_id=rec.id, session_id=rec.session_id, student_id=rec.student_id,
                                    old_status=rec.status, new_status=new_status, method=method,
                                    note=new_note if new_note != rec.note else None, user_id=actor.id, at=now))
            return MarkResult(True, "success", f"Đã cập nhật: {C.STATUS_LABELS[new_status]}", info, new_status,
                              None if unmark else now, None if unmark else actor.full_name, method,
                              rec.version + 1)
    except PermissionDenied as exc:
        return MarkResult(False, "denied", str(exc))
    except SQLAlchemyError:
        log.exception("set_status failed")
        return MarkResult(False, "error", "Lỗi kết nối cơ sở dữ liệu – CHƯA ghi nhận. Vui lòng thử lại.")


def bulk_set(actor: Actor, session_id: int, record_ids: list[int], new_status: str, *,
             only_unmarked: bool = True) -> MarkResult:
    """Đặt trạng thái cho nhiều em trong một giao dịch."""
    if new_status not in C.MARKED_STATUSES:
        return MarkResult(False, "invalid", "Trạng thái không hợp lệ.")
    try:
        actor.require(P_ATTEND)
        with session_scope() as s:
            sess = s.get(AttendanceSession, session_id)
            if sess is None:
                return MarkResult(False, "invalid", "Không tìm thấy phiên.")
            blocked = _check_session_writable(actor, sess)
            if blocked:
                return blocked
            scope = sessions_svc.actor_classes_in_session(actor, sess)
            stmt = select(AttendanceRecord).where(AttendanceRecord.session_id == session_id,
                                                  AttendanceRecord.id.in_(record_ids))
            now, changed, skipped = utcnow(), 0, 0
            for rec in s.scalars(stmt).all():
                if (scope is not None and rec.class_id not in scope) or rec.status == new_status:
                    skipped += 1
                    continue
                cond = [AttendanceRecord.id == rec.id, AttendanceRecord.version == rec.version]
                if only_unmarked:
                    cond.append(AttendanceRecord.status == C.UNMARKED)
                res = s.execute(update(AttendanceRecord).where(*cond).values(
                    status=new_status, method=C.METHOD_BULK, marked_by=actor.id, marked_at=now,
                    version=AttendanceRecord.version + 1).execution_options(synchronize_session=False))
                if res.rowcount == 1:
                    s.add(AttendanceLog(record_id=rec.id, session_id=session_id, student_id=rec.student_id,
                                        old_status=rec.status, new_status=new_status, method=C.METHOD_BULK,
                                        user_id=actor.id, at=now))
                    changed += 1
                else:
                    skipped += 1
            msg = f"Đã cập nhật {changed} em"
            if skipped:
                msg += f", bỏ qua {skipped} em (đã có trạng thái hoặc ngoài phạm vi)"
            return MarkResult(True, "success", msg + ".", status=new_status, version=changed)
    except PermissionDenied as exc:
        return MarkResult(False, "denied", str(exc))
    except SQLAlchemyError:
        log.exception("bulk_set failed")
        return MarkResult(False, "error", "Lỗi kết nối cơ sở dữ liệu – CHƯA ghi nhận. Vui lòng thử lại.")


def resolve_student(s, raw: str, method: str, accept_plain_code: bool) -> tuple[Student | None, MarkResult | None]:
    text = (raw or "").strip()
    if not text:
        return None, MarkResult(False, "invalid", "Mã trống.")
    if text.upper().startswith(config.QR_PREFIX):
        token = text[len(config.QR_PREFIX):].strip().upper()
        cred = s.scalar(select(QrCredential).where(QrCredential.token == token))
        if cred is None:
            return None, MarkResult(False, "invalid", "Mã QR không thuộc hệ thống.")
        if cred.status != "active":
            st = s.get(Student, cred.student_id)
            return None, MarkResult(False, "revoked", "Mã QR này đã bị thu hồi. Hãy dùng thẻ mới.",
                                    _student_info(st, None) if st else {})
        return s.get(Student, cred.student_id), None
    if method == C.METHOD_CODE or accept_plain_code:
        st = s.scalar(select(Student).where(Student.code == normalize_code(text)))
        if st is None:
            return None, MarkResult(False, "invalid", f"Không tìm thấy mã thiếu nhi '{text[:32]}'.")
        return st, None
    return None, MarkResult(False, "invalid", "Mã QR không hợp lệ (không phải thẻ của Xứ đoàn).")


def check_in(actor: Actor, session_id: int, raw: str | None = None, *, student_id: int | None = None,
             method: str = C.METHOD_QR, accept_plain_code: bool = False,
             at_local: datetime | None = None) -> MarkResult:
    """Điểm danh 1 em bằng QR / mã (hoặc student_id đã được người dùng xác nhận).
    Chỉ ghi khi em đang 'Chưa điểm danh'."""
    try:
        actor.require(P_ATTEND)
        with session_scope() as s:
            sess = s.get(AttendanceSession, session_id)
            if sess is None:
                return MarkResult(False, "invalid", "Không tìm thấy phiên.")
            if sess.status != C.SESSION_OPEN:
                return MarkResult(False, "closed", "Phiên không ở trạng thái đang mở.")
            if not sessions_svc.can_view_session(actor, sess):
                return MarkResult(False, "denied", "Bạn không được phân công cho phiên này.")
            if student_id is not None:
                st = s.get(Student, student_id)
                if st is None:
                    return MarkResult(False, "invalid", "Không tìm thấy thiếu nhi.")
            else:
                st, err = resolve_student(s, raw, method, accept_plain_code)
                if err:
                    return err
            rec = s.scalar(select(AttendanceRecord).where(AttendanceRecord.session_id == session_id,
                                                          AttendanceRecord.student_id == st.id))
            class_name = s.scalar(select(ClassGroup.name).where(ClassGroup.id == rec.class_id)) if rec else None
            info = _student_info(st, class_name)
            if rec is None:
                return MarkResult(False, "not_in_session",
                                  f"{info['saint_name']} {info['full_name']} không thuộc danh sách phiên này.".strip(),
                                  info)
            if rec.status != C.UNMARKED:
                return MarkResult(False, "duplicate", "Em đã được điểm danh trước đó.", info, rec.status,
                                  rec.marked_at, _marker_name(s, rec.marked_by), rec.method, rec.version)
            new_status = status_for_arrival(sess, at_local)
            now = utcnow()
            res = s.execute(
                update(AttendanceRecord)
                .where(AttendanceRecord.id == rec.id, AttendanceRecord.status == C.UNMARKED)
                .values(status=new_status, method=method, marked_by=actor.id, marked_at=now,
                        version=AttendanceRecord.version + 1)
                .execution_options(synchronize_session=False)
            )
            if res.rowcount != 1:  # một Huynh trưởng khác vừa quét cùng lúc
                s.rollback()
                fresh = s.get(AttendanceRecord, rec.id)
                s.refresh(fresh)
                return MarkResult(False, "duplicate", "Em vừa được người khác điểm danh.", info, fresh.status,
                                  fresh.marked_at, _marker_name(s, fresh.marked_by), fresh.method, fresh.version)
            s.add(AttendanceLog(record_id=rec.id, session_id=session_id, student_id=st.id, old_status=C.UNMARKED,
                                new_status=new_status, method=method, user_id=actor.id, at=now))
            return MarkResult(True, "success", C.STATUS_LABELS[new_status], info, new_status, now,
                              actor.full_name, method, rec.version + 1)
    except PermissionDenied as exc:
        return MarkResult(False, "denied", str(exc))
    except SQLAlchemyError:
        log.exception("check_in failed")
        return MarkResult(False, "error", "Lỗi kết nối cơ sở dữ liệu – CHƯA ghi nhận. Vui lòng quét lại.")


def student_session_summary(student_id: int, year_id: int) -> pd.DataFrame:
    with session_scope() as s:
        rows = s.execute(
            select(AttendanceSession.session_date, AttendanceSession.title, AttendanceSession.activity_type,
                   AttendanceRecord.status, AttendanceRecord.method, AttendanceRecord.marked_at, AttendanceRecord.note)
            .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
            .where(AttendanceRecord.student_id == student_id, AttendanceSession.school_year_id == year_id)
            .order_by(AttendanceSession.session_date.desc())
        ).all()
    return pd.DataFrame(rows, columns=["date", "title", "activity_type", "status", "method", "marked_at", "note"])


def is_today(d: date) -> bool:
    return d == now_local().date()
