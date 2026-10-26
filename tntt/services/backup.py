"""Sao lưu / khôi phục toàn bộ dữ liệu dưới dạng ZIP (mỗi bảng 1 file JSON).

Dùng được cho cả SQLite và PostgreSQL, và để chuyển dữ liệu giữa hai loại.
Khôi phục chạy trong MỘT giao dịch: lỗi giữa chừng -> dữ liệu cũ giữ nguyên.
"""
from __future__ import annotations

import base64
import io
import json
import zipfile
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Integer, LargeBinary, Time, delete, func, insert, select, text

from .. import __version__
from ..db import SCHEMA_VERSION, get_engine
from ..models import Base, utcnow
from ..security import P_BACKUP, Actor
from . import audit

FORMAT = "tntt-backup"


def _encode(value):
    if isinstance(value, bytes):
        return {"__b64__": base64.b64encode(value).decode()}
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _decode(value, coltype):
    if value is None:
        return None
    if isinstance(value, dict) and "__b64__" in value:
        return base64.b64decode(value["__b64__"])
    if isinstance(coltype, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(coltype, Date):
        return date.fromisoformat(value)
    if isinstance(coltype, Time):
        return time.fromisoformat(value)
    if isinstance(coltype, Boolean):
        return bool(value)
    if isinstance(coltype, Integer):
        return int(value)
    if isinstance(coltype, LargeBinary) and isinstance(value, str):
        return base64.b64decode(value)
    return value


def export_backup(actor: Actor) -> bytes:
    actor.require(P_BACKUP)
    engine = get_engine()
    buf = io.BytesIO()
    counts = {}
    with engine.connect() as conn, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in Base.metadata.sorted_tables:
            rows = [{k: _encode(v) for k, v in r._mapping.items()} for r in conn.execute(select(table))]
            counts[table.name] = len(rows)
            zf.writestr(f"{table.name}.json", json.dumps(rows, ensure_ascii=False))
        zf.writestr("manifest.json", json.dumps({
            "format": FORMAT, "schema_version": SCHEMA_VERSION, "app_version": __version__,
            "created_at": utcnow().isoformat(), "dialect": engine.dialect.name, "counts": counts,
        }, ensure_ascii=False, indent=2))
    audit.log(actor, "backup.export", "database", None, counts=counts)
    return buf.getvalue()


def read_manifest(data: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ValueError("File sao lưu không hợp lệ.") from exc
    if manifest.get("format") != FORMAT:
        raise ValueError("File không phải bản sao lưu của hệ thống này.")
    if int(manifest.get("schema_version", 0)) > SCHEMA_VERSION:
        raise ValueError("Bản sao lưu được tạo từ phiên bản mới hơn. Hãy cập nhật ứng dụng trước.")
    return manifest


def restore_backup(actor: Actor, data: bytes) -> dict:
    """Thay TOÀN BỘ dữ liệu hiện tại bằng dữ liệu trong bản sao lưu."""
    actor.require(P_BACKUP)
    manifest = read_manifest(data)
    engine = get_engine()
    counts = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf, engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA defer_foreign_keys=ON"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
        for table in Base.metadata.sorted_tables:
            name = f"{table.name}.json"
            if name not in zf.namelist():
                continue
            rows = json.loads(zf.read(name))
            cols = {c.name: c.type for c in table.columns}
            clean = [{k: _decode(v, cols[k]) for k, v in r.items() if k in cols} for r in rows]
            for i in range(0, len(clean), 500):
                if clean[i:i + 500]:
                    conn.execute(insert(table), clean[i:i + 500])
            counts[table.name] = len(clean)
        if engine.dialect.name == "postgresql":
            for table in Base.metadata.sorted_tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and isinstance(pk[0].type, Integer) and pk[0].autoincrement in (True, "auto"):
                    max_id = conn.execute(select(func.max(pk[0]))).scalar() or 0
                    conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', '{pk[0].name}'), "
                        f"{max(max_id, 1)}, {'true' if max_id else 'false'})"))
    from . import branding

    branding.invalidate()
    # Tài khoản đang thao tác có thể không còn trong dữ liệu vừa khôi phục -> không gắn user_id.
    audit.log(None, "backup.restore", "database", None, by=actor.username,
              source_created_at=manifest.get("created_at"), counts=counts)
    return counts
