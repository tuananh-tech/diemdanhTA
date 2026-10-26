"""Nhật ký hoạt động (đăng nhập, chỉnh sửa, xuất dữ liệu...)."""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_engine, session_scope
from ..models import AuditLog
from ..security import Actor


def record(session: Session, actor: Actor | None, action: str, entity: str | None = None,
           entity_id=None, **details) -> None:
    """Ghi nhật ký trong CÙNG giao dịch với thao tác nghiệp vụ."""
    session.add(
        AuditLog(
            user_id=actor.id if actor else None,
            username=actor.username if actor else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
        )
    )


def log(actor: Actor | None, action: str, entity: str | None = None, entity_id=None, **details) -> None:
    with session_scope() as s:
        record(s, actor, action, entity, entity_id, **details)


def list_audit(since: datetime | None = None, until: datetime | None = None,
               action_prefix: str | None = None, username: str | None = None,
               limit: int = 500) -> pd.DataFrame:
    stmt = select(AuditLog.at, AuditLog.username, AuditLog.action, AuditLog.entity,
                  AuditLog.entity_id, AuditLog.details).order_by(AuditLog.at.desc()).limit(limit)
    if since:
        stmt = stmt.where(AuditLog.at >= since)
    if until:
        stmt = stmt.where(AuditLog.at < until)
    if action_prefix:
        stmt = stmt.where(AuditLog.action.like(f"{action_prefix}%"))
    if username:
        stmt = stmt.where(AuditLog.username == username)
    with get_engine().connect() as conn:
        return pd.read_sql(stmt, conn)
