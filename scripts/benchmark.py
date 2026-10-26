"""Đo hiệu năng với quy mô Xứ đoàn lớn (dữ liệu giả lập).

Chạy:  python scripts/benchmark.py            (SQLite tạm)
       BENCH_DB=postgres python scripts/benchmark.py   (PostgreSQL nhúng – cần pgserver)
"""
from __future__ import annotations

import io
import os
import random
import sys
import tempfile
import time
from datetime import date, time as dtime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SETUP_TOKEN", "bench")

from tntt import constants as C, db  # noqa: E402
from tntt.services import attendance, importer, org, qrcodes, reports, sessions, students, users  # noqa: E402

N_STUDENTS = 1200
N_SESSIONS = 40
RESULTS = []


def timed(label: str, fn, *a, **k):
    t = time.perf_counter()
    out = fn(*a, **k)
    ms = (time.perf_counter() - t) * 1000
    RESULTS.append((label, ms))
    print(f"{label:<58} {ms:>9.0f} ms", flush=True)
    return out


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tntt_bench_"))
    url = f"sqlite:///{(tmp / 'bench.db').as_posix()}"
    if os.environ.get("BENCH_DB") == "postgres":
        import pgserver

        url = pgserver.get_server(str(tmp / "pg"), cleanup_mode="stop").get_uri()
    db.configure(url)
    db.init_db()
    print("CSDL:", db.get_engine().dialect.name)
    admin = users.create_first_admin("bench", "admin", "Admin", "Admin12345")
    year = org.current_year()

    rng = random.Random(1)
    classes = [f"Lớp {i + 1:02d}" for i in range(30)]
    df = pd.DataFrame({
        "Mã": [f"{i:05d}" for i in range(1, N_STUDENTS + 1)],
        "Tên Thánh": [rng.choice(["Maria", "Giuse", "Phêrô", "Anna"]) for _ in range(N_STUDENTS)],
        "Họ và tên": [f"Nguyễn Văn Em {i}" for i in range(N_STUDENTS)],
        "Ngành": [rng.choice(["Ấu Nhi", "Thiếu Nhi", "Nghĩa Sĩ"]) for _ in range(N_STUDENTS)],
        "Lớp": [classes[i % 30] for i in range(N_STUDENTS)],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    raw = timed(f"Đọc Excel {N_STUDENTS} dòng", importer.read_raw, buf.getvalue(), "x.xlsx")
    table = importer.table_from_raw(raw, 0)
    plan = timed("Lập kế hoạch nhập (kiểm lỗi, trùng)", importer.build_plan, table, importer.auto_map(list(table.columns)),
                 importer.ImportOptions())
    timed("Áp dụng nhập vào CSDL (1 giao dịch)", importer.apply_plan, admin, plan, year.id)

    sids = []
    start = date.today() - timedelta(days=N_SESSIONS * 7)
    for i in range(N_SESSIONS):
        d = start + timedelta(days=7 * i)
        sid = sessions.create_session(admin, year_id=year.id, title=f"Buổi {i}", activity_type=C.ACTIVITY_TYPES[i % 3],
                                      session_date=d, start_time=dtime(8, 0), late_after=dtime(8, 15), class_ids=[],
                                      scope_all=True, open_now=False)
        sids.append(sid)
    timed(f"Mở 1 phiên toàn Xứ đoàn (lập danh sách {N_STUDENTS} em)", sessions.open_session, admin, sids[0])
    for sid in sids[1:]:
        sessions.open_session(admin, sid)
    t = time.perf_counter()
    for sid in sids[1:]:
        roster = attendance.roster_frame(sid)
        ids = [int(x) for x in roster.record_id]
        rng.shuffle(ids)
        cut = int(len(ids) * 0.8)
        attendance.bulk_set(admin, sid, ids[:cut], C.PRESENT)
        attendance.bulk_set(admin, sid, ids[cut:cut + len(ids) // 10], C.ABSENT)
    print(f"(nạp dữ liệu {N_SESSIONS - 1} phiên × {N_STUDENTS} em: {time.perf_counter() - t:.1f}s)")

    timed("Tải danh sách điểm danh 1 phiên (1.200 em)", attendance.roster_frame, sids[0])
    timed("Tải danh sách 1 lớp trong phiên", attendance.roster_frame, sids[0],
          class_ids={next(iter(org.class_options(year.id)))})
    timed("Đếm trạng thái phiên", attendance.session_counts, sids[0])
    all_ids = list(students.students_frame(year.id, admin)["id"])[:300]
    tokens = qrcodes.ensure_tokens(admin, all_ids)
    times = []
    for s_id in all_ids:
        t = time.perf_counter()
        attendance.check_in(admin, sids[0], qrcodes.payload_for(tokens[s_id]))
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    RESULTS.append(("Quét QR: trung bình / p95 (300 lượt)", sum(times) / len(times)))
    print(f"{'Quét QR (300 lượt): trung bình':<58} {sum(times) / len(times):>9.1f} ms   p95 {times[int(.95 * len(times))]:.1f} ms")
    timed("Danh sách thiếu nhi + tìm kiếm không dấu", students.students_frame, year.id, admin, search="nguyen van em 11")
    frame = timed(f"Tải dữ liệu báo cáo cả năm (~{N_STUDENTS * N_SESSIONS:,} bản ghi)", reports.attendance_frame,
                  year.id, admin)
    timed("Thống kê theo lớp", reports.group_stats, frame, "class_name")
    timed("Thống kê theo tháng", lambda: reports.group_stats(reports.add_period(frame, "month", year), "period"))
    timed("Thống kê từng em (1.200 em)", reports.student_stats, frame)
    timed("Sổ điểm danh (em × buổi)", reports.attendance_matrix, frame)
    timed("Danh sách buổi sinh hoạt", sessions.list_sessions, year.id, admin)
    print(f"\nTổng số bản ghi: {len(frame):,}")


if __name__ == "__main__":
    main()
