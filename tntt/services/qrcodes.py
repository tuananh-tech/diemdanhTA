"""Quản lý QR credential: cấp, thu hồi, cấp lại.

Nội dung QR = "TNTT:" + token ngẫu nhiên 12 ký tự. Không chứa họ tên, ngày sinh
hay mã thiếu nhi -> nhặt được thẻ cũng không suy ra thông tin cá nhân, và hệ
thống không có trang công khai nào tra cứu theo token.
"""
from __future__ import annotations

import secrets

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import config
from ..db import session_scope
from ..models import QrCredential, Student, User, utcnow
from ..security import P_QR, Actor, PermissionDenied
from . import audit, org
from .students import get_enrollment

# Bỏ các ký tự dễ nhầm (0/O, 1/I/L, U/V). Tất cả thuộc bảng "alphanumeric" của QR.
TOKEN_ALPHABET = "ABCDEFGHJKMNPQRSTWXYZ23456789"
TOKEN_LENGTH = 12


def new_token() -> str:
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


def payload_for(token: str) -> str:
    return f"{config.QR_PREFIX}{token}"


def _check_scope(actor: Actor, student_ids: list[int], year_id: int | None) -> None:
    actor.require(P_QR)
    if actor.is_global:
        return
    if year_id is None:
        raise PermissionDenied("Thiếu năm học để kiểm tra phạm vi.")
    classes = []
    for sid in student_ids:
        enr = get_enrollment(sid, year_id)
        classes.append(enr.class_id if enr else None)
    org.ensure_class_access(actor, year_id, classes)


def active_tokens(student_ids: list[int]) -> dict[int, str]:
    if not student_ids:
        return {}
    with session_scope() as s:
        rows = s.execute(select(QrCredential.student_id, QrCredential.token).where(
            QrCredential.student_id.in_(student_ids), QrCredential.status == "active")).all()
    return dict(rows)


def ensure_tokens(actor: Actor, student_ids: list[int], year_id: int | None = None) -> dict[int, str]:
    """Trả về token đang hiệu lực; em nào chưa có thì cấp mới."""
    _check_scope(actor, student_ids, year_id)
    tokens = active_tokens(student_ids)
    missing = [sid for sid in student_ids if sid not in tokens]
    if missing:
        with session_scope() as s:
            for sid in missing:
                token = new_token()
                s.add(QrCredential(student_id=sid, token=token, status="active", issued_by=actor.id))
                tokens[sid] = token
            audit.record(s, actor, "qr.issue", "student", None, count=len(missing))
    return tokens


def reissue(actor: Actor, student_id: int, reason: str, year_id: int | None = None) -> str:
    """Thu hồi mã cũ (mất thẻ, lộ mã...) và cấp mã mới trong một giao dịch."""
    _check_scope(actor, [student_id], year_id)
    for _ in range(3):
        try:
            with session_scope() as s:
                now = utcnow()
                for cred in s.scalars(select(QrCredential).where(
                        QrCredential.student_id == student_id, QrCredential.status == "active")).all():
                    cred.status, cred.revoked_at, cred.revoked_by = "revoked", now, actor.id
                    cred.revoke_reason = (reason or "Cấp lại")[:255]
                s.flush()
                token = new_token()
                s.add(QrCredential(student_id=student_id, token=token, status="active", issued_by=actor.id))
                audit.record(s, actor, "qr.reissue", "student", student_id, reason=reason)
                return token
        except IntegrityError:  # trùng token (xác suất cực nhỏ) hoặc cấp đồng thời -> thử lại
            continue
    raise RuntimeError("Không cấp được mã mới, vui lòng thử lại.")


def revoke(actor: Actor, student_id: int, reason: str, year_id: int | None = None) -> int:
    _check_scope(actor, [student_id], year_id)
    with session_scope() as s:
        n = 0
        for cred in s.scalars(select(QrCredential).where(
                QrCredential.student_id == student_id, QrCredential.status == "active")).all():
            cred.status, cred.revoked_at, cred.revoked_by = "revoked", utcnow(), actor.id
            cred.revoke_reason = (reason or "Thu hồi")[:255]
            n += 1
        audit.record(s, actor, "qr.revoke", "student", student_id, reason=reason)
        return n


def history(student_id: int) -> pd.DataFrame:
    with session_scope() as s:
        rows = s.execute(
            select(QrCredential.token, QrCredential.status, QrCredential.issued_at, User.full_name,
                   QrCredential.revoked_at, QrCredential.revoke_reason)
            .join(User, User.id == QrCredential.issued_by, isouter=True)
            .where(QrCredential.student_id == student_id).order_by(QrCredential.issued_at.desc())
        ).all()
    df = pd.DataFrame(rows, columns=["token", "status", "issued_at", "issued_by", "revoked_at", "reason"])
    df["token"] = df["token"].map(lambda t: t[:4] + "••••••" + t[-2:])  # không hiển thị đầy đủ
    return df


def student_for_token(token: str) -> Student | None:
    with session_scope() as s:
        cred = s.scalar(select(QrCredential).where(QrCredential.token == token, QrCredential.status == "active"))
        return s.get(Student, cred.student_id) if cred else None
