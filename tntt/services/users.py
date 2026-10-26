"""Tài khoản, xác thực và phạm vi phân quyền."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
from sqlalchemy import delete, func, select

from .. import config
from .. import constants as C
from ..db import session_scope
from ..models import Branch, ClassGroup, LoginSession, User, UserScope, utcnow
from ..security import (
    P_USERS,
    Actor,
    PermissionDenied,
    hash_password,
    password_problems,
    verify_password,
)
from . import audit

log = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")
_DUMMY_HASH = hash_password(secrets.token_hex(8))


class AuthError(Exception):
    pass


@dataclass
class LoginResult:
    ok: bool
    message: str
    actor: Actor | None = None
    must_change_password: bool = False


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_username(username: str) -> str:
    username = normalize_username(username)
    if not _USERNAME_RE.match(username):
        raise ValueError("Tên đăng nhập 3–64 ký tự, chỉ gồm chữ thường không dấu, số, dấu . _ -")
    return username


# ---- Khởi tạo lần đầu -----------------------------------------------------
def has_users() -> bool:
    with session_scope() as s:
        return s.scalar(select(func.count(User.id))) > 0


_generated_setup_token: str | None = None


def setup_token() -> str:
    """Token bắt buộc khi tạo quản trị viên đầu tiên.

    Lấy từ SETUP_TOKEN (secrets/env). Nếu chưa cấu hình, sinh ngẫu nhiên và chỉ
    in ra log máy chủ (người vận hành mới xem được) -> người lạ mở web trước
    không thể chiếm quyền quản trị.
    """
    global _generated_setup_token
    configured = config.get_setting("SETUP_TOKEN")
    if configured:
        return str(configured)
    if _generated_setup_token is None:
        _generated_setup_token = secrets.token_urlsafe(9)
        log.warning("=" * 60)
        log.warning("SETUP TOKEN (dùng 1 lần để tạo tài khoản quản trị): %s", _generated_setup_token)
        log.warning("=" * 60)
        print(f"\n*** SETUP TOKEN de tao tai khoan quan tri: {_generated_setup_token} ***\n", flush=True)
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            (config.DATA_DIR / "SETUP_TOKEN.txt").write_text(_generated_setup_token, encoding="utf-8")
        except OSError:
            pass
    return _generated_setup_token


def create_first_admin(token: str, username: str, full_name: str, password: str) -> Actor:
    if not hmac.compare_digest(str(token).strip(), setup_token()):
        raise AuthError("Mã khởi tạo (setup token) không đúng.")
    username = validate_username(username)
    problems = password_problems(password)
    if problems:
        raise ValueError(" ".join(problems))
    with session_scope() as s:
        if s.scalar(select(func.count(User.id))) > 0:
            raise AuthError("Hệ thống đã có tài khoản. Hãy đăng nhập.")
        user = User(username=username, full_name=full_name.strip() or username,
                    password_hash=hash_password(password), role=C.ROLE_ADMIN,
                    must_change_password=False)
        s.add(user)
        s.flush()
        actor = Actor(user.id, user.username, user.full_name, user.role)
        audit.record(s, actor, "user.bootstrap_admin", "user", user.id)
    try:
        (config.DATA_DIR / "SETUP_TOKEN.txt").unlink(missing_ok=True)
    except OSError:
        pass
    return actor


# ---- Đăng nhập ------------------------------------------------------------
def _load_scopes(s, user: User) -> tuple[set[int], set[int]]:
    rows = s.execute(select(UserScope.branch_id, UserScope.class_id).where(UserScope.user_id == user.id)).all()
    return {b for b, _ in rows if b}, {c for _, c in rows if c}


def actor_for(user_id: int) -> Actor | None:
    """Nạp lại người dùng mỗi lượt chạy -> khóa/đổi quyền có hiệu lực ngay."""
    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None or not user.is_active:
            return None
        branches, classes = _load_scopes(s, user)
        return Actor(user.id, user.username, user.full_name, user.role, branches, classes)


def authenticate(username: str, password: str) -> LoginResult:
    username = normalize_username(username)
    generic = "Tên đăng nhập hoặc mật khẩu không đúng."
    with session_scope() as s:
        user = s.scalar(select(User).where(User.username == username))
        if user is None:
            verify_password(password, _DUMMY_HASH)  # cân bằng thời gian phản hồi
            audit.record(s, None, "auth.login_failed", "user", None, username=username)
            return LoginResult(False, generic)
        now = utcnow()
        if user.locked_until and user.locked_until > now:
            minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
            return LoginResult(False, f"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau {minutes} phút.")
        if not verify_password(password, user.password_hash):
            user.failed_attempts += 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_attempts = 0
            audit.record(s, None, "auth.login_failed", "user", user.id, username=username)
            return LoginResult(False, generic)
        if not user.is_active:
            return LoginResult(False, "Tài khoản đã bị vô hiệu hóa. Liên hệ quản trị viên.")
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        branches, classes = _load_scopes(s, user)
        actor = Actor(user.id, user.username, user.full_name, user.role, branches, classes)
        audit.record(s, actor, "auth.login", "user", user.id)
        return LoginResult(True, "Đăng nhập thành công.", actor, user.must_change_password)


# ---- Ghi nhớ đăng nhập (sống sót khi tải lại trang) --------------------------
REMEMBER_MAX_HOURS = 14 * 24


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_token(user_id: int, user_agent: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    with session_scope() as s:
        s.add(LoginSession(user_id=user_id, token_hash=_token_hash(token), created_at=now, last_seen_at=now,
                           expires_at=now + timedelta(hours=REMEMBER_MAX_HOURS), user_agent=(user_agent or "")[:255]))
    return token


def resolve_login_token(token: str | None) -> LoginResult | None:
    """Token hợp lệ, chưa hết hạn tuyệt đối, chưa quá thời gian không hoạt động, tài khoản còn hiệu lực."""
    if not token or len(token) > 200:
        return None
    now = utcnow()
    idle = timedelta(minutes=config.session_idle_minutes())
    with session_scope() as s:
        row = s.scalar(select(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
        if row is None:
            return None
        if row.expires_at < now or row.last_seen_at + idle < now:
            s.delete(row)
            return None
        user = s.get(User, row.user_id)
        if user is None or not user.is_active:
            s.delete(row)
            return None
        row.last_seen_at = now
        branches, classes = _load_scopes(s, user)
        actor = Actor(user.id, user.username, user.full_name, user.role, branches, classes)
        return LoginResult(True, "", actor, user.must_change_password)


def touch_login_token(token: str | None) -> None:
    if not token:
        return
    with session_scope() as s:
        row = s.scalar(select(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
        if row:
            row.last_seen_at = utcnow()


def revoke_login_token(token: str | None) -> None:
    if not token:
        return
    with session_scope() as s:
        s.execute(delete(LoginSession).where(LoginSession.token_hash == _token_hash(token)))


def _revoke_all(s, user_id: int) -> None:
    s.execute(delete(LoginSession).where(LoginSession.user_id == user_id))


def change_password(actor: Actor, old_password: str, new_password: str) -> None:
    problems = password_problems(new_password)
    if problems:
        raise ValueError(" ".join(problems))
    with session_scope() as s:
        user = s.get(User, actor.id)
        if user is None or not verify_password(old_password, user.password_hash):
            raise AuthError("Mật khẩu hiện tại không đúng.")
        if verify_password(new_password, user.password_hash):
            raise ValueError("Mật khẩu mới phải khác mật khẩu cũ.")
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        _revoke_all(s, user.id)
        audit.record(s, actor, "user.change_password", "user", user.id)


# ---- Quản lý tài khoản (admin) -------------------------------------------
def list_users() -> pd.DataFrame:
    with session_scope() as s:
        users = s.scalars(select(User).order_by(User.role, User.username)).all()
        branch_names = dict(s.execute(select(Branch.id, Branch.name)).all())
        class_names = dict(s.execute(select(ClassGroup.id, ClassGroup.name)).all())
        rows = []
        for u in users:
            scope_labels = []
            for sc in u.scopes:
                if sc.branch_id:
                    scope_labels.append(f"Ngành {branch_names.get(sc.branch_id, '?')}")
                if sc.class_id:
                    scope_labels.append(f"Lớp {class_names.get(sc.class_id, '?')}")
            rows.append({
                "id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
                "is_active": u.is_active, "locked": bool(u.locked_until and u.locked_until > utcnow()),
                "last_login_at": u.last_login_at, "scopes": ", ".join(scope_labels),
                "branch_ids": [sc.branch_id for sc in u.scopes if sc.branch_id],
                "class_ids": [sc.class_id for sc in u.scopes if sc.class_id],
            })
    return pd.DataFrame(rows)


def create_user(actor: Actor, username: str, full_name: str, role: str, password: str,
                branch_ids=(), class_ids=()) -> int:
    actor.require(P_USERS)
    username = validate_username(username)
    if role not in C.ROLE_LABELS:
        raise ValueError("Vai trò không hợp lệ.")
    problems = password_problems(password)
    if problems:
        raise ValueError(" ".join(problems))
    with session_scope() as s:
        if s.scalar(select(User.id).where(User.username == username)):
            raise ValueError("Tên đăng nhập đã tồn tại.")
        user = User(username=username, full_name=full_name.strip() or username, role=role,
                    password_hash=hash_password(password), must_change_password=True)
        user.scopes = [UserScope(branch_id=b) for b in branch_ids] + [UserScope(class_id=c) for c in class_ids]
        s.add(user)
        s.flush()
        audit.record(s, actor, "user.create", "user", user.id, username=username, role=role)
        return user.id


def update_user(actor: Actor, user_id: int, *, full_name: str, role: str, is_active: bool,
                branch_ids=(), class_ids=()) -> None:
    actor.require(P_USERS)
    if role not in C.ROLE_LABELS:
        raise ValueError("Vai trò không hợp lệ.")
    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            raise ValueError("Không tìm thấy tài khoản.")
        if user.id == actor.id and (role != C.ROLE_ADMIN or not is_active):
            raise PermissionDenied("Không thể tự hạ quyền hoặc vô hiệu hóa chính mình.")
        if user.role == C.ROLE_ADMIN and (role != C.ROLE_ADMIN or not is_active):
            other_admins = s.scalar(select(func.count(User.id)).where(
                User.role == C.ROLE_ADMIN, User.is_active.is_(True), User.id != user.id))
            if other_admins == 0:
                raise PermissionDenied("Phải còn ít nhất một quản trị viên đang hoạt động.")
        user.full_name = full_name.strip() or user.username
        user.role = role
        user.is_active = is_active
        if not is_active:
            _revoke_all(s, user.id)
        user.scopes.clear()
        s.flush()
        user.scopes.extend([UserScope(branch_id=b) for b in branch_ids] + [UserScope(class_id=c) for c in class_ids])
        audit.record(s, actor, "user.update", "user", user.id, role=role, is_active=is_active,
                     branch_ids=list(branch_ids), class_ids=list(class_ids))


def reset_password(actor: Actor, user_id: int, new_password: str) -> None:
    actor.require(P_USERS)
    problems = password_problems(new_password)
    if problems:
        raise ValueError(" ".join(problems))
    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            raise ValueError("Không tìm thấy tài khoản.")
        user.password_hash = hash_password(new_password)
        user.must_change_password = True
        user.failed_attempts = 0
        user.locked_until = None
        _revoke_all(s, user.id)
        audit.record(s, actor, "user.reset_password", "user", user.id)


def unlock_user(actor: Actor, user_id: int) -> None:
    actor.require(P_USERS)
    with session_scope() as s:
        user = s.get(User, user_id)
        if user:
            user.locked_until = None
            user.failed_attempts = 0
            audit.record(s, actor, "user.unlock", "user", user.id)


def user_options() -> dict[int, str]:
    with session_scope() as s:
        rows = s.execute(select(User.id, User.full_name, User.username).where(User.is_active.is_(True))
                         .order_by(User.full_name)).all()
    return {i: f"{n} ({u})" for i, n, u in rows}
