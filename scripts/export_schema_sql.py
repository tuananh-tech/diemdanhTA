"""Sinh migrations/001_initial_schema.sql (PostgreSQL) từ models.py.

Ứng dụng TỰ tạo bảng khi khởi động (db.init_db), nên file này chỉ cần khi bạn
muốn tạo CSDL thủ công trong Supabase SQL Editor hoặc để rà soát cấu trúc.
Chạy lại script mỗi khi đổi models.py:  python scripts/export_schema_sql.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tntt.db import SCHEMA_VERSION  # noqa: E402
from tntt.models import Base  # noqa: E402


def main() -> None:
    dialect = postgresql.dialect()
    out = [
        "-- HỆ THỐNG ĐIỂM DANH TNTT – lược đồ PostgreSQL / Supabase",
        f"-- Phiên bản lược đồ: {SCHEMA_VERSION}. File được sinh tự động từ tntt/models.py – KHÔNG sửa tay.",
        "-- Ứng dụng tự tạo bảng khi khởi động; chỉ chạy file này nếu muốn khởi tạo thủ công.",
        "BEGIN;",
        "",
    ]
    for table in Base.metadata.sorted_tables:
        out.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in sorted(table.indexes, key=lambda i: i.name):
            out.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        out.append("")
    out.append("-- Supabase mở REST API công khai cho schema public: bật RLS (không policy) để khóa truy cập")
    out.append("-- bằng anon/authenticated key. Ứng dụng kết nối bằng vai trò chủ sở hữu bảng nên không bị ảnh hưởng.")
    for table in Base.metadata.sorted_tables:
        out.append(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY;')
    out.append("")
    out.append(f"INSERT INTO schema_meta (version, applied_at) VALUES ({SCHEMA_VERSION}, now());")
    out.append("COMMIT;")
    target = ROOT / "migrations" / "001_initial_schema.sql"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("Đã ghi", target)


if __name__ == "__main__":
    main()
