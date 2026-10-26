import pytest

from tntt import constants as C
from tntt.security import PermissionDenied
from tntt.services import users


def test_bootstrap_requires_token(database):
    assert not users.has_users()
    with pytest.raises(users.AuthError):
        users.create_first_admin("wrong", "admin", "A", "Admin12345")
    actor = users.create_first_admin("test-setup-token", "Admin", "A", "Admin12345")
    assert actor.username == "admin" and actor.role == C.ROLE_ADMIN
    with pytest.raises(users.AuthError):  # chỉ được khởi tạo 1 lần
        users.create_first_admin("test-setup-token", "admin2", "B", "Admin12345")


def test_login_and_lockout(admin):
    assert users.authenticate("admin", "Admin12345").ok
    assert not users.authenticate("admin", "sai").ok
    assert not users.authenticate("khongco", "x").ok
    for _ in range(users.MAX_FAILED_ATTEMPTS):
        users.authenticate("admin", "sai")
    res = users.authenticate("admin", "Admin12345")
    assert not res.ok and "tạm khóa" in res.message
    users.unlock_user(admin, admin.id)
    assert users.authenticate("admin", "Admin12345").ok


def test_change_password_and_must_change(admin):
    uid = users.create_user(admin, "ht.an", "HT An", C.ROLE_LEADER, "Temp12345")
    res = users.authenticate("ht.an", "Temp12345")
    assert res.ok and res.must_change_password
    users.change_password(res.actor, "Temp12345", "NewPass123")
    res2 = users.authenticate("ht.an", "NewPass123")
    assert res2.ok and not res2.must_change_password
    with pytest.raises(users.AuthError):
        users.change_password(res2.actor, "sai", "Another123")
    assert uid


def test_only_admin_manages_users_and_last_admin_protected(admin):
    uid = users.create_user(admin, "bdh", "BĐH", C.ROLE_COORDINATOR, "Coord12345")
    coord = users.actor_for(uid)
    with pytest.raises(PermissionDenied):
        users.create_user(coord, "x1", "X", C.ROLE_LEADER, "Xxxxx12345")
    with pytest.raises(PermissionDenied):
        users.update_user(admin, admin.id, full_name="A", role=C.ROLE_LEADER, is_active=True)


def test_remember_token_lifecycle(admin, monkeypatch):
    from datetime import timedelta

    from tntt.db import session_scope
    from tntt.models import LoginSession

    token = users.create_login_token(admin.id, "pytest")
    with session_scope() as s:  # chỉ lưu bản băm
        assert s.query(LoginSession).filter_by(token_hash=token).count() == 0
    res = users.resolve_login_token(token)
    assert res and res.actor.id == admin.id
    assert users.resolve_login_token("token-gia") is None
    users.revoke_login_token(token)
    assert users.resolve_login_token(token) is None
    # hết hạn do không hoạt động
    t2 = users.create_login_token(admin.id)
    with session_scope() as s:
        row = s.query(LoginSession).one()
        row.last_seen_at -= timedelta(days=2)
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "60")
    assert users.resolve_login_token(t2) is None
    # đổi mật khẩu -> thu hồi mọi phiên ghi nhớ
    t3 = users.create_login_token(admin.id)
    users.change_password(admin, "Admin12345", "Admin67890")
    assert users.resolve_login_token(t3) is None


def test_disabled_user_cannot_login_and_session_revoked(admin):
    uid = users.create_user(admin, "tam", "Tâm", C.ROLE_LEADER, "Tam123456")
    users.update_user(admin, uid, full_name="Tâm", role=C.ROLE_LEADER, is_active=False)
    assert not users.authenticate("tam", "Tam123456").ok
    assert users.actor_for(uid) is None
