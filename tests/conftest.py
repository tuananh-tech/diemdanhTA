from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tntt import constants as C  # noqa: E402
from tntt import db  # noqa: E402
from tntt.security import Actor  # noqa: E402
from tntt.services import branding, org, users  # noqa: E402
from tntt.services.students import StudentInput, save_student  # noqa: E402


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    """PostgreSQL thật (nhúng qua pgserver) khi chạy: TEST_DB=postgres pytest"""
    import os

    if os.environ.get("TEST_DB", "sqlite") != "postgres":
        return None
    pgserver = pytest.importorskip("pgserver")
    srv = pgserver.get_server(str(tmp_path_factory.mktemp("pg")), cleanup_mode="stop")
    return srv.get_uri().replace("postgresql://", "postgresql+psycopg2://")


@pytest.fixture()
def database(tmp_path, monkeypatch, pg_url):
    monkeypatch.setenv("SETUP_TOKEN", "test-setup-token")
    if pg_url:
        from sqlalchemy import text

        url = pg_url
        engine = db.configure(url)
        with engine.begin() as conn:  # CSDL sạch cho từng test
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    else:
        url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        db.configure(url)
    db.init_db()
    branding.invalidate()
    yield url
    db.get_engine().dispose()
    branding.invalidate()


@pytest.fixture()
def admin(database) -> Actor:
    return users.create_first_admin("test-setup-token", "admin", "Quản trị", "Admin12345")


@pytest.fixture()
def year(database):
    return org.current_year()


@pytest.fixture()
def school(admin, year):
    """2 lớp, mỗi lớp 5 em + 1 em tạm nghỉ."""
    branches = {b.name: b.id for b in org.list_branches()}
    c1 = org.save_class(admin, year.id, "Ấu Nhi 1", branches["Ấu Nhi"])
    c2 = org.save_class(admin, year.id, "Thiếu Nhi 1", branches["Thiếu Nhi"])
    ids = {c1: [], c2: []}
    n = 0
    for cid in (c1, c2):
        for i in range(5):
            n += 1
            ids[cid].append(save_student(admin, StudentInput(code=f"{n:04d}", full_name=f"Nguyễn Văn Em{n}",
                                                             saint_name="Giuse"), year.id, cid))
    inactive = save_student(admin, StudentInput(code="0099", full_name="Trần Tạm Nghỉ", status="inactive"),
                            year.id, c1)
    return {"year": year, "c1": c1, "c2": c2, "students": ids, "inactive": inactive,
            "branches": branches}


@pytest.fixture()
def leader(admin, school) -> Actor:
    uid = users.create_user(admin, "htlop1", "Huynh trưởng Lớp 1", C.ROLE_LEADER, "Leader12345",
                            class_ids=[school["c1"]])
    return users.actor_for(uid)


def make_session(actor, school, classes=None, **kw):
    from tntt.services import sessions

    params = dict(year_id=school["year"].id, title="Giáo lý", activity_type="Giáo lý",
                  session_date=kw.pop("session_date", date.today()), start_time=time(8, 0),
                  late_after=kw.pop("late_after", time(8, 15)), class_ids=classes or [school["c1"], school["c2"]])
    params.update(kw)
    return sessions.create_session(actor, **params)
