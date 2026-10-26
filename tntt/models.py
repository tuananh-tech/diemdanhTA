"""Mô hình dữ liệu (SQLAlchemy 2). Chạy được trên PostgreSQL/Supabase và SQLite.

Nguyên tắc:
- Hồ sơ thiếu nhi (students) tách khỏi ghi danh theo năm học (enrollments).
- Mỗi (phiên, thiếu nhi) chỉ có MỘT bản ghi điểm danh: ràng buộc UNIQUE ở DB.
- Mọi thay đổi trạng thái được ghi vào attendance_logs.
- Thời điểm (DateTime) lưu theo UTC không kèm tz; ngày/giờ của phiên lưu theo giờ VN.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from . import constants as C


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Base(DeclarativeBase):
    pass


class SchemaMeta(Base):
    __tablename__ = "schema_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --------------------------------------------------------------------------
# Tài khoản & phân quyền
# --------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"role IN ({_in(C.ROLE_LABELS)})", name="ck_users_role"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=C.ROLE_LEADER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    scopes: Mapped[list["UserScope"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class LoginSession(Base):
    """Phiên "ghi nhớ đăng nhập": trình duyệt giữ token ngẫu nhiên trong cookie,
    CSDL chỉ lưu bản băm SHA-256 -> lộ CSDL cũng không dùng được token."""

    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))


class UserScope(Base):
    """Phạm vi dữ liệu của Huynh trưởng / người xem: theo ngành hoặc theo lớp."""

    __tablename__ = "user_scopes"
    __table_args__ = (
        CheckConstraint(
            "branch_id IS NOT NULL OR class_id IS NOT NULL", name="ck_scope_target"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="scopes")


# --------------------------------------------------------------------------
# Năm học, ngành, lớp
# --------------------------------------------------------------------------
class SchoolYear(Base):
    __tablename__ = "school_years"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    semester2_start: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#1B2A4A")


class ClassGroup(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("school_year_id", "name", name="uq_class_year_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_year_id: Mapped[int] = mapped_column(ForeignKey("school_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(255))


# --------------------------------------------------------------------------
# Thiếu nhi
# --------------------------------------------------------------------------
class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(C.STUDENT_STATUS_LABELS)})", name="ck_students_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    saint_name: Mapped[str | None] = mapped_column(String(60))
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    search_text: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(1))
    parent_name: Mapped[str | None] = mapped_column(String(120))
    parent_phone: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Enrollment(Base):
    """Ghi danh của một thiếu nhi trong một năm học (lớp, đội). Giữ lịch sử nhiều năm."""

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "school_year_id", name="uq_enrollment_student_year"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    school_year_id: Mapped[int] = mapped_column(ForeignKey("school_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"), index=True)
    team: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------
# Phiên điểm danh
# --------------------------------------------------------------------------
class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(C.SESSION_STATUS_LABELS)})", name="ck_sessions_status"),
        Index("ix_sessions_year_date", "school_year_id", "session_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    school_year_id: Mapped[int] = mapped_column(ForeignKey("school_years.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    late_after: Mapped[time | None] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=C.SESSION_SCHEDULED)
    scope_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class SessionClass(Base):
    __tablename__ = "session_classes"
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="CASCADE"), primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), primary_key=True)


class AttendanceRecord(Base):
    """Trạng thái chính thức duy nhất của một thiếu nhi trong một phiên."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_record_session_student"),
        CheckConstraint(f"status IN ({_in(C.STATUSES)})", name="ck_records_status"),
        Index("ix_records_student", "student_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    # Lớp tại thời điểm lập danh sách phiên -> báo cáo lịch sử không đổi khi chuyển lớp.
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=C.UNMARKED)
    method: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(255))
    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    marked_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (Index("ix_attlog_session", "session_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_records.id", ondelete="SET NULL"))
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# --------------------------------------------------------------------------
# QR credentials
# --------------------------------------------------------------------------
class QrCredential(Base):
    __tablename__ = "qr_credentials"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_qr_status"),
        # Mỗi thiếu nhi chỉ có tối đa 1 mã đang hiệu lực.
        Index(
            "uq_qr_one_active_per_student",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    revoke_reason: Mapped[str | None] = mapped_column(String(255))


# --------------------------------------------------------------------------
# Cấu hình, tài nguyên, nhật ký
# --------------------------------------------------------------------------
class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Asset(Base):
    """Ảnh (logo...) lưu trong DB để bền vững cả trên Streamlit Cloud (ổ đĩa tạm)."""

    __tablename__ = "assets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False, default="image/png")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_at", "at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------
# Module khuôn mặt (tùy chọn, mặc định tắt)
# --------------------------------------------------------------------------
class FaceConsent(Base):
    __tablename__ = "face_consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    guardian_name: Mapped[str] = mapped_column(String(120), nullable=False)
    relation: Mapped[str] = mapped_column(String(40), nullable=False)
    consent_date: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    document_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)
    withdrawn_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class FaceTemplate(Base):
    """Chỉ lưu vector đặc trưng (embedding), KHÔNG lưu ảnh khuôn mặt."""

    __tablename__ = "face_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_id: Mapped[int] = mapped_column(ForeignKey("face_consents.id", ondelete="CASCADE"), nullable=False)
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
