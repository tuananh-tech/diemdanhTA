"""Kết nối CSDL, phiên giao dịch và khởi tạo/migration."""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import date
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import config
from . import constants as C
from .models import Base, Branch, SchemaMeta, SchoolYear

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_lock = threading.Lock()
_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker] = {}
_current_url: str | None = None


def _make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - chạy khi kết nối
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            if ":memory:" not in url:
                cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        connect_args={"connect_timeout": 10, "application_name": "tntt-diemdanh"},
        future=True,
    )


def configure(url: str | None = None) -> Engine:
    """Chọn CSDL đang dùng (mặc định theo cấu hình). Dùng được trong test."""
    global _current_url
    url = config.normalize_url(url) if url else config.database_url()
    with _lock:
        if url not in _engines:
            _engines[url] = _make_engine(url)
            _sessionmakers[url] = sessionmaker(bind=_engines[url], expire_on_commit=False, future=True)
        _current_url = url
    return _engines[url]


def get_engine() -> Engine:
    if _current_url is None:
        configure()
    return _engines[_current_url]


def is_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


@contextmanager
def session_scope() -> Iterator[Session]:
    """Một giao dịch: commit khi thành công, rollback toàn bộ khi có lỗi."""
    if _current_url is None:
        configure()
    session: Session = _sessionmakers[_current_url]()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --------------------------------------------------------------------------
# Migration
# --------------------------------------------------------------------------
def _enable_rls(conn) -> None:
    """Supabase mở API REST công khai cho schema public. Bật RLS (không policy)
    để khóa toàn bộ truy cập bằng anon/authenticated key; ứng dụng kết nối
    trực tiếp bằng vai trò chủ sở hữu bảng nên không bị ảnh hưởng."""
    for table in Base.metadata.sorted_tables:
        conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))


MIGRATIONS: dict[int, callable] = {
    # version: hàm(conn) – thêm migration mới ở đây, KHÔNG sửa migration cũ.
}


def current_schema_version(engine: Engine) -> int:
    if not inspect(engine).has_table("schema_meta"):
        return 0
    with engine.connect() as conn:
        row = conn.execute(select(SchemaMeta.version).order_by(SchemaMeta.id.desc()).limit(1)).first()
    return int(row[0]) if row else 0


def init_db(seed: bool = True) -> None:
    """Tạo bảng (idempotent), chạy migration còn thiếu, bật RLS, nạp dữ liệu mặc định."""
    engine = get_engine()
    version = current_schema_version(engine)
    with engine.begin() as conn:
        if version == 0:
            Base.metadata.create_all(conn)
            conn.execute(SchemaMeta.__table__.insert().values(version=SCHEMA_VERSION))
            version = SCHEMA_VERSION
        for v in sorted(MIGRATIONS):
            if v > version:
                MIGRATIONS[v](conn)
                conn.execute(SchemaMeta.__table__.insert().values(version=v))
                version = v
        if engine.dialect.name == "postgresql":
            _enable_rls(conn)
    if seed:
        seed_defaults()


def default_year_bounds(today: date | None = None) -> tuple[str, date, date, date]:
    """Năm học TNTT thường từ tháng 8/9 đến tháng 6/7 năm sau."""
    today = today or date.today()
    start_year = today.year if today.month >= 8 else today.year - 1
    return (
        f"{start_year}-{start_year + 1}",
        date(start_year, 8, 1),
        date(start_year + 1, 7, 31),
        date(start_year + 1, 1, 1),
    )


def seed_defaults() -> None:
    with session_scope() as s:
        if s.scalar(select(Branch.id).limit(1)) is None:
            for i, (name, color) in enumerate(C.DEFAULT_BRANCHES):
                s.add(Branch(name=name, color=color, sort_order=i))
        if s.scalar(select(SchoolYear.id).limit(1)) is None:
            name, start, end, sem2 = default_year_bounds()
            s.add(SchoolYear(name=name, start_date=start, end_date=end, semester2_start=sem2, is_current=True))
