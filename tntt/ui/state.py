"""Trạng thái phiên làm việc trên giao diện: người dùng, năm học, thông báo."""
from __future__ import annotations

import time
from contextlib import contextmanager

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from .. import config
from ..security import Actor, PermissionDenied
from ..services import org, users


COOKIE = "tntt_sess"


def login(actor: Actor, must_change: bool, remember: bool = True, token: str | None = None) -> None:
    st.session_state["uid"] = actor.id
    st.session_state["last_seen"] = time.time()
    st.session_state["must_change_password"] = must_change
    if remember and token is None:
        ua = st.context.headers.get("User-Agent") if hasattr(st, "context") else None
        token = users.create_login_token(actor.id, ua)
        st.session_state["_cookie_op"] = ("set", token)
    st.session_state["_login_token"] = token


def logout() -> None:
    users.revoke_login_token(st.session_state.get("_login_token") or _cookie_token())
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state["_cookie_op"] = ("clear", "")


def _cookie_token() -> str | None:
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:  # noqa: BLE001
        return None


def apply_cookie_op() -> None:
    """Ghi/xóa cookie qua iframe cùng nguồn (Streamlit không có API đặt cookie phía server)."""
    op = st.session_state.pop("_cookie_op", None)
    if not op:
        return
    import streamlit.components.v1 as components

    kind, token = op
    max_age = users.REMEMBER_MAX_HOURS * 3600 if kind == "set" else 0
    components.html(
        "<script>(function(){var s=location.protocol==='https:'?';secure':'';"
        f"document.cookie='{COOKIE}={token if kind == 'set' else ''};path=/;max-age={max_age};samesite=strict'+s;"
        "})();</script>", height=0)


def current_actor() -> Actor | None:
    uid = st.session_state.get("uid")
    if not uid:
        # Phiên Streamlit mới (tải lại trang / mở lại tab): khôi phục từ cookie nếu hợp lệ.
        token = _cookie_token()
        res = users.resolve_login_token(token) if token else None
        if res is None:
            return None
        login(res.actor, res.must_change_password, token=token)
        return res.actor
    idle = time.time() - st.session_state.get("last_seen", 0)
    if idle > config.session_idle_minutes() * 60:
        logout()
        st.session_state["flash"] = ("warning", "Phiên đăng nhập đã hết hạn do không hoạt động. Vui lòng đăng nhập lại.")
        return None
    actor = users.actor_for(uid)  # tài khoản bị khóa/đổi quyền -> có hiệu lực ngay
    if actor is None:
        logout()
        st.session_state["flash"] = ("error", "Tài khoản không còn hiệu lực.")
        return None
    if time.time() - st.session_state.get("_touched", 0) > 60:  # gia hạn token tối đa 1 lần/phút
        users.touch_login_token(st.session_state.get("_login_token"))
        st.session_state["_touched"] = time.time()
    st.session_state["last_seen"] = time.time()
    return actor


def actor() -> Actor:
    """Người dùng đã xác thực ở đầu lượt chạy (main.run)."""
    return st.session_state["_actor"]


PAGES: dict = {}  # url_path -> st.Page của lượt chạy hiện tại (main._pages điền vào)


def go_to(url_path: str) -> None:
    page = PAGES.get(url_path)
    if page is not None:
        st.switch_page(page)


def year_id() -> int:
    if "year_id" not in st.session_state:
        y = org.current_year()
        st.session_state["year_id"] = y.id if y else None
    return st.session_state["year_id"]


def year():
    return org.get_year(year_id())


def flash(kind: str, message: str) -> None:
    """Thông báo hiển thị ở lượt chạy kế tiếp (sau st.rerun)."""
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if item:
        kind, message = item
        getattr(st, kind, st.info)(message)


@contextmanager
def guard(success: str | None = None):
    """Bắt lỗi nghiệp vụ và hiển thị thân thiện, không lộ chi tiết kỹ thuật."""
    try:
        yield
        if success:
            st.toast(success, icon="✅")
    except PermissionDenied as exc:
        st.error(f"⛔ {exc}")
    except (ValueError, users.AuthError) as exc:
        st.error(str(exc))
    except SQLAlchemyError:
        st.error("Không kết nối được cơ sở dữ liệu hoặc dữ liệu bị xung đột. Thao tác CHƯA được lưu – vui lòng thử lại.")
