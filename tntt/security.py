"""Băm mật khẩu, vai trò, quyền và phạm vi dữ liệu."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from . import constants as C

# ---- Mật khẩu (PBKDF2-SHA256, thư viện chuẩn, không cần dependency ngoài) ----
_ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Mật khẩu cần ít nhất {MIN_PASSWORD_LENGTH} ký tự.")
    if password.isdigit() or password.isalpha():
        problems.append("Mật khẩu nên có cả chữ và số.")
    return problems


def generate_password(length: int = 12) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if not password_problems(pw):
            return pw


# ---- Quyền ----------------------------------------------------------------
P_USERS = "users.manage"
P_SETTINGS = "settings.manage"
P_BACKUP = "backup.manage"
P_AUDIT = "audit.view"
P_STUDENTS_VIEW = "students.view"
P_STUDENTS_EDIT = "students.edit"
P_STUDENTS_IMPORT = "students.import"
P_CLASSES = "classes.manage"
P_SESSIONS = "sessions.manage"
P_ATTEND = "attendance.mark"
P_ATTEND_CLOSED = "attendance.edit_closed"
P_REPORTS = "reports.view"
P_QR = "qr.manage"
P_FACE = "face.manage"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    C.ROLE_ADMIN: {
        P_USERS, P_SETTINGS, P_BACKUP, P_AUDIT, P_STUDENTS_VIEW, P_STUDENTS_EDIT,
        P_STUDENTS_IMPORT, P_CLASSES, P_SESSIONS, P_ATTEND, P_ATTEND_CLOSED,
        P_REPORTS, P_QR, P_FACE,
    },
    C.ROLE_COORDINATOR: {
        P_AUDIT, P_STUDENTS_VIEW, P_STUDENTS_EDIT, P_STUDENTS_IMPORT, P_CLASSES,
        P_SESSIONS, P_ATTEND, P_ATTEND_CLOSED, P_REPORTS, P_QR, P_FACE,
    },
    C.ROLE_LEADER: {P_STUDENTS_VIEW, P_STUDENTS_EDIT, P_SESSIONS, P_ATTEND, P_REPORTS, P_QR},
    C.ROLE_VIEWER: {P_STUDENTS_VIEW, P_REPORTS},
}

# Vai trò thấy toàn bộ dữ liệu; các vai trò khác bị giới hạn theo user_scopes.
GLOBAL_ROLES = {C.ROLE_ADMIN, C.ROLE_COORDINATOR}


class PermissionDenied(Exception):
    pass


@dataclass
class Actor:
    """Người dùng đang thao tác (đã xác thực)."""

    id: int | None
    username: str
    full_name: str
    role: str
    branch_ids: set[int] = field(default_factory=set)
    class_ids: set[int] = field(default_factory=set)

    @property
    def is_global(self) -> bool:
        return self.role in GLOBAL_ROLES

    def can(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")


SYSTEM_ACTOR = Actor(id=None, username="system", full_name="Hệ thống", role=C.ROLE_ADMIN)
