import threading
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import func, select

from tntt import config
from tntt import constants as C
from tntt.db import session_scope
from tntt.models import AttendanceLog, AttendanceRecord
from tntt.security import PermissionDenied
from tntt.services import attendance, qrcodes, sessions

from .conftest import make_session


def _rec(session_id, student_id):
    with session_scope() as s:
        return s.scalar(select(AttendanceRecord).where(AttendanceRecord.session_id == session_id,
                                                       AttendanceRecord.student_id == student_id))


def test_roster_built_from_scope_and_unmarked_by_default(admin, school):
    sid = make_session(admin, school, classes=[school["c1"]])
    counts = attendance.session_counts(sid)
    assert counts["total"] == 5  # em tạm nghỉ không thuộc đối tượng
    assert counts[C.UNMARKED] == 5 and counts[C.ABSENT] == 0  # chưa quét KHÔNG phải vắng


def test_manual_mark_change_and_log(admin, school):
    sid = make_session(admin, school)
    roster = attendance.roster_frame(sid)
    rid, ver = int(roster.record_id[0]), int(roster.version[0])
    r1 = attendance.set_status(admin, rid, C.PRESENT, expected_version=ver)
    assert r1.ok and r1.version == ver + 1 and r1.marked_by == admin.full_name
    r2 = attendance.set_status(admin, rid, C.EXCUSED, note="Ốm", expected_version=r1.version)
    assert r2.ok
    # phiên bản cũ -> xung đột, không ghi đè
    r3 = attendance.set_status(admin, rid, C.ABSENT, expected_version=ver)
    assert not r3.ok and r3.kind == "conflict" and r3.status == C.EXCUSED
    hist = attendance.record_history(rid)
    assert list(hist["new_status"]) == [C.EXCUSED, C.PRESENT]
    assert attendance.set_status(admin, rid, C.UNMARKED).ok
    assert _rec(sid, int(roster.student_id[0])).marked_at is None


def test_qr_checkin_duplicate_and_multiple_sessions(admin, school):
    s1 = make_session(admin, school, title="Thánh lễ", activity_type="Thánh lễ")
    s2 = make_session(admin, school, title="Sinh hoạt", activity_type="Sinh hoạt TNTT")
    stu = school["students"][school["c1"]][0]
    token = qrcodes.ensure_tokens(admin, [stu])[stu]
    payload = qrcodes.payload_for(token)
    morning = datetime.combine(date.today(), time(8, 5), tzinfo=config.LOCAL_TZ)
    r = attendance.check_in(admin, s1, payload, at_local=morning)
    assert r.ok and r.status == C.PRESENT and r.student["code"] == "0001"
    dup = attendance.check_in(admin, s1, payload, at_local=morning)
    assert not dup.ok and dup.kind == "duplicate" and dup.marked_by == admin.full_name
    # cùng em, phiên khác -> ghi nhận độc lập
    assert attendance.check_in(admin, s2, payload, at_local=morning).ok
    with session_scope() as s:
        n = s.scalar(select(func.count(AttendanceRecord.id)).where(AttendanceRecord.student_id == stu,
                                                                   AttendanceRecord.status != C.UNMARKED))
    assert n == 2


def test_late_detection(admin, school):
    sid = make_session(admin, school, late_after=time(8, 15))
    stu = school["students"][school["c2"]][0]
    payload = qrcodes.payload_for(qrcodes.ensure_tokens(admin, [stu])[stu])
    late = datetime.combine(date.today(), time(8, 40), tzinfo=config.LOCAL_TZ)
    assert attendance.check_in(admin, sid, payload, at_local=late).status == C.LATE


def test_invalid_revoked_not_in_session_and_manual_code(admin, school):
    sid = make_session(admin, school, classes=[school["c1"]])
    assert attendance.check_in(admin, sid, "https://example.com").kind == "invalid"
    assert attendance.check_in(admin, sid, "TNTT:KHONGTONTAI").kind == "invalid"
    other = school["students"][school["c2"]][0]
    tok = qrcodes.ensure_tokens(admin, [other])[other]
    assert attendance.check_in(admin, sid, qrcodes.payload_for(tok)).kind == "not_in_session"
    stu = school["students"][school["c1"]][1]
    old = qrcodes.ensure_tokens(admin, [stu])[stu]
    new = qrcodes.reissue(admin, stu, "Mất thẻ")
    assert old != new
    assert attendance.check_in(admin, sid, qrcodes.payload_for(old)).kind == "revoked"
    assert attendance.check_in(admin, sid, qrcodes.payload_for(new)).ok
    # nhập mã thủ công (camera hỏng)
    r = attendance.check_in(admin, sid, "0003", method=C.METHOD_CODE)
    assert r.ok and r.method == C.METHOD_CODE
    # mã trần trong QR bị từ chối nếu không bật tương thích
    assert attendance.check_in(admin, sid, "0004").kind == "invalid"
    assert attendance.check_in(admin, sid, "0004", accept_plain_code=True).ok


def test_qr_and_manual_share_single_official_status(admin, school):
    sid = make_session(admin, school)
    stu = school["students"][school["c1"]][0]
    rec = _rec(sid, stu)
    attendance.set_status(admin, rec.id, C.EXCUSED)
    payload = qrcodes.payload_for(qrcodes.ensure_tokens(admin, [stu])[stu])
    r = attendance.check_in(admin, sid, payload)
    assert r.kind == "duplicate" and r.status == C.EXCUSED  # QR không ghi đè trạng thái thủ công
    with session_scope() as s:
        assert s.scalar(select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.session_id == sid, AttendanceRecord.student_id == stu)) == 1


def test_bulk_mark_only_unmarked(admin, school):
    sid = make_session(admin, school, classes=[school["c1"]])
    roster = attendance.roster_frame(sid)
    attendance.set_status(admin, int(roster.record_id[0]), C.ABSENT)
    res = attendance.bulk_set(admin, sid, [int(x) for x in roster.record_id], C.PRESENT)
    assert res.ok and res.version == 4
    counts = attendance.session_counts(sid)
    assert counts[C.PRESENT] == 4 and counts[C.ABSENT] == 1


def test_close_session_and_permissions(admin, leader, school):
    sid = make_session(admin, school, classes=[school["c1"]])
    roster = attendance.roster_frame(sid)
    attendance.set_status(leader, int(roster.record_id[0]), C.PRESENT)
    changed = sessions.close_session(admin, sid, mark_unmarked_as=C.ABSENT)
    assert changed == 4
    assert attendance.session_counts(sid)[C.ABSENT] == 4
    # leader không sửa được phiên đã đóng; admin được
    r = attendance.set_status(leader, int(roster.record_id[1]), C.EXCUSED)
    assert not r.ok and r.kind == "closed"
    assert attendance.set_status(admin, int(roster.record_id[1]), C.EXCUSED).ok
    assert attendance.check_in(admin, sid, "0001", method=C.METHOD_CODE).kind == "closed"


def test_leader_scope_in_sessions(admin, leader, school):
    sid = make_session(admin, school)  # cả 2 lớp
    roster = attendance.roster_frame(sid)
    other = roster[roster.class_id == school["c2"]].iloc[0]
    r = attendance.set_status(leader, int(other.record_id), C.PRESENT)
    assert not r.ok and r.kind == "denied"
    # leader không tạo được phiên cho lớp ngoài phạm vi / toàn xứ đoàn
    with pytest.raises(PermissionDenied):
        make_session(leader, school, classes=[school["c2"]])
    with pytest.raises(PermissionDenied):
        make_session(leader, school, scope_all=True)
    own = make_session(leader, school, classes=[school["c1"]])
    assert own
    # phiên chỉ của lớp 2 -> leader lớp 1 không thấy
    only2 = make_session(admin, school, classes=[school["c2"]])
    ids = set(sessions.list_sessions(school["year"].id, leader)["id"])
    assert sid in ids and own in ids and only2 not in ids


def test_sync_roster_adds_new_and_removes_unmarked(admin, school):
    from tntt.services.students import StudentInput, save_student, transfer_students

    sid = make_session(admin, school, classes=[school["c1"]])
    new = save_student(admin, StudentInput(code="0500", full_name="Mới Vào"), school["year"].id, school["c1"])
    moved = school["students"][school["c1"]][0]
    transfer_students(admin, [moved], school["year"].id, school["c2"])
    res = sessions.sync_roster(admin, sid)
    assert res == {"added": 1, "removed": 1}
    assert _rec(sid, new) is not None and _rec(sid, moved) is None


def test_scheduled_session_and_recurring(admin, school):
    sid = make_session(admin, school, open_now=False)
    assert attendance.session_counts(sid)["total"] == 0
    assert attendance.check_in(admin, sid, "0001", method=C.METHOD_CODE).kind == "closed"
    sessions.open_session(admin, sid)
    assert attendance.session_counts(sid)["total"] == 10
    start = date(2030, 1, 1)
    res = sessions.create_recurring(admin, year_id=school["year"].id, start=start, end=start + timedelta(days=27),
                                    weekdays=[6], activity_type="Thánh lễ", start_time=time(7, 0), late_minutes=10,
                                    class_ids=[], scope_all=True)
    assert res == {"created": 4, "skipped": 0}
    again = sessions.create_recurring(admin, year_id=school["year"].id, start=start, end=start + timedelta(days=27),
                                      weekdays=[6], activity_type="Thánh lễ", start_time=time(7, 0), late_minutes=10,
                                      class_ids=[], scope_all=True)
    assert again == {"created": 0, "skipped": 4}


def test_concurrent_scans_same_student_only_one_wins(admin, school):
    """8 Huynh trưởng quét cùng 1 thẻ cùng lúc -> đúng 1 bản ghi thành công, 1 dòng log."""
    sid = make_session(admin, school)
    stu = school["students"][school["c1"]][2]
    payload = qrcodes.payload_for(qrcodes.ensure_tokens(admin, [stu])[stu])
    barrier = threading.Barrier(8)
    results = []

    def worker():
        barrier.wait()
        results.append(attendance.check_in(admin, sid, payload))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r.ok for r in results) == 1
    assert all(r.kind == "duplicate" for r in results if not r.ok)
    with session_scope() as s:
        logs = s.scalar(select(func.count(AttendanceLog.id)).where(AttendanceLog.session_id == sid,
                                                                    AttendanceLog.student_id == stu))
    assert logs == 1


def test_concurrent_scans_many_students(admin, school):
    sid = make_session(admin, school)
    all_students = school["students"][school["c1"]] + school["students"][school["c2"]]
    tokens = qrcodes.ensure_tokens(admin, all_students)
    payloads = [qrcodes.payload_for(tokens[s]) for s in all_students] * 3  # mỗi thẻ quét 3 lần
    results, lock = [], threading.Lock()

    def worker(chunk):
        for p in chunk:
            r = attendance.check_in(admin, sid, p)
            with lock:
                results.append(r)

    threads = [threading.Thread(target=worker, args=(payloads[i::4],)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r.ok for r in results) == 10
    assert attendance.session_counts(sid)[C.UNMARKED] == 0


def test_database_failure_records_nothing(admin, school, monkeypatch):
    from sqlalchemy.exc import OperationalError

    sid = make_session(admin, school)
    stu = school["students"][school["c1"]][0]
    payload = qrcodes.payload_for(qrcodes.ensure_tokens(admin, [stu])[stu])
    original_add = None

    from sqlalchemy.orm import Session

    original_add = Session.add

    def failing_add(self, obj, *a, **k):
        if isinstance(obj, AttendanceLog):
            raise OperationalError("INSERT", {}, Exception("mất kết nối"))
        return original_add(self, obj, *a, **k)

    monkeypatch.setattr(Session, "add", failing_add)
    r = attendance.check_in(admin, sid, payload)
    monkeypatch.setattr(Session, "add", original_add)
    assert not r.ok and r.kind == "error"
    assert _rec(sid, stu).status == C.UNMARKED  # không có bản ghi "nửa vời"
