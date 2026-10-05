from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from enum import Enum

import bcrypt
import streamlit as st
from sqlalchemy import delete, func, select
from streamlit.errors import StreamlitSecretNotFoundError

from browser_session import COOKIE_NAME
from database import session_scope
from models import Employee, EmployeeSession
from utils import now_sp

PERSISTENT_SESSION_DAYS = 90


class AdminRole(str, Enum):
    ANALISTA = "ANALISTA"
    GESTOR = "GESTOR"


def _secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError, StreamlitSecretNotFoundError):
        return ""


def _configured_accounts() -> list[tuple[str, str, AdminRole]]:
    legacy_username = _secret("ADMIN_USERNAME")
    legacy_hash = _secret("ADMIN_PASSWORD_HASH")
    analyst_hash = _secret("ANALYST_PASSWORD_HASH") or legacy_hash
    manager_hash = _secret("MANAGER_PASSWORD_HASH") or legacy_hash
    accounts: list[tuple[str, str, AdminRole]] = []
    if analyst_hash:
        accounts.append(
            (
                _secret("ANALYST_USERNAME") or "analista",
                analyst_hash,
                AdminRole.ANALISTA,
            )
        )
    if manager_hash:
        accounts.append(
            (
                _secret("MANAGER_USERNAME") or "gestor",
                manager_hash,
                AdminRole.GESTOR,
            )
        )
    # Mantém o login administrativo antigo como um alias do analista.
    if (
        legacy_username
        and legacy_hash
        and legacy_username not in {account[0] for account in accounts}
    ):
        accounts.append((legacy_username, legacy_hash, AdminRole.ANALISTA))
    return accounts


def auth_configured() -> bool:
    return bool(_configured_accounts())


def verify_credentials(username: str, password: str) -> AdminRole | None:
    supplied_username = username.strip()
    for expected_user, password_hash, role in _configured_accounts():
        if not hmac.compare_digest(supplied_username, expected_user):
            continue
        try:
            if bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
                return role
        except (ValueError, TypeError):
            return None
    return None


def is_authenticated() -> bool:
    return bool(st.session_state.get("admin_authenticated", False))


def is_employee_authenticated() -> bool:
    return bool(st.session_state.get("employee_authenticated", False))


def current_employee_id() -> int | None:
    if not is_employee_authenticated():
        return None
    try:
        return int(st.session_state["employee_id"])
    except (KeyError, TypeError, ValueError):
        return None


def _employee_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _browser_employee_token() -> str:
    try:
        return str(st.context.cookies.get(COOKIE_NAME, "")).strip()
    except (AttributeError, RuntimeError):
        return ""


def restore_employee_login() -> bool:
    if is_authenticated() or is_employee_authenticated():
        return is_employee_authenticated()
    if st.session_state.get("clear_persistent_employee_cookie"):
        return False
    token = _browser_employee_token()
    if not token:
        return False
    with session_scope() as session:
        timestamp = now_sp()
        session.execute(
            delete(EmployeeSession).where(EmployeeSession.expires_at <= timestamp)
        )
        employee = session.scalar(
            select(Employee)
            .join(EmployeeSession, EmployeeSession.employee_id == Employee.id)
            .where(
                EmployeeSession.token_hash == _employee_token_hash(token),
                EmployeeSession.expires_at > timestamp,
                Employee.active.is_(True),
            )
        )
        if not employee:
            return False
        employee_id = employee.id
        employee_name = employee.name
    st.session_state["employee_authenticated"] = True
    st.session_state["employee_id"] = employee_id
    st.session_state["employee_name"] = employee_name
    st.session_state["active_employee_session_token"] = token
    return True


def consume_new_employee_token() -> str:
    return str(st.session_state.pop("new_employee_session_token", ""))


def consume_cookie_clear_request() -> bool:
    return bool(st.session_state.pop("clear_persistent_employee_cookie", False))


def current_admin_role() -> AdminRole | None:
    if not is_authenticated():
        return None
    try:
        return AdminRole(st.session_state.get("admin_role", AdminRole.ANALISTA.value))
    except ValueError:
        return None


def current_admin_username() -> str:
    return str(st.session_state.get("admin_username", "")).strip()


def switch_admin_role(role: AdminRole | str) -> AdminRole:
    if not is_authenticated():
        raise PermissionError("É necessário estar autenticado para trocar o perfil.")
    selected_role = role if isinstance(role, AdminRole) else AdminRole(str(role))
    st.session_state["admin_role"] = selected_role.value
    st.session_state.pop("opened_rdv_id", None)
    return selected_role


def login(username: str, password: str) -> bool:
    role = verify_credentials(username, password)
    if role:
        st.session_state["admin_authenticated"] = True
        st.session_state["admin_username"] = username.strip()
        st.session_state["admin_role"] = role.value
        return True
    return False


def login_employee(username: str, password: str) -> bool:
    supplied_username = username.strip()
    if not supplied_username or not password:
        return False
    with session_scope() as session:
        employee = session.scalar(
            select(Employee).where(
                func.lower(Employee.username) == supplied_username.lower(),
                Employee.active.is_(True),
            )
        )
        if not employee or not employee.password_hash:
            return False
        try:
            valid = bcrypt.checkpw(
                password.encode("utf-8"), employee.password_hash.encode("utf-8")
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            return False
        timestamp = now_sp()
        token = secrets.token_urlsafe(32)
        session.execute(
            delete(EmployeeSession).where(EmployeeSession.expires_at <= timestamp)
        )
        session.add(
            EmployeeSession(
                employee_id=employee.id,
                token_hash=_employee_token_hash(token),
                expires_at=timestamp + timedelta(days=PERSISTENT_SESSION_DAYS),
                created_at=timestamp,
            )
        )
        session.flush()
        employee_id = employee.id
        employee_name = employee.name
    st.session_state["employee_authenticated"] = True
    st.session_state["employee_id"] = employee_id
    st.session_state["employee_name"] = employee_name
    st.session_state["new_employee_session_token"] = token
    st.session_state["active_employee_session_token"] = token
    return True


def logout() -> None:
    employee_token = _browser_employee_token()
    active_token = str(st.session_state.get("active_employee_session_token", ""))
    pending_token = str(st.session_state.get("new_employee_session_token", ""))
    token_to_revoke = employee_token or active_token or pending_token
    if token_to_revoke:
        with session_scope() as session:
            session.execute(
                delete(EmployeeSession).where(
                    EmployeeSession.token_hash == _employee_token_hash(token_to_revoke)
                )
            )
    if token_to_revoke or is_employee_authenticated():
        st.session_state["clear_persistent_employee_cookie"] = True
    for key in (
        "admin_authenticated",
        "admin_username",
        "admin_role",
        "selected_rdv_id",
        "opened_rdv_id",
        "test_role_switcher",
        "employee_authenticated",
        "employee_id",
        "employee_name",
        "post_login_redirect",
        "new_employee_session_token",
        "active_employee_session_token",
    ):
        st.session_state.pop(key, None)


def generate_password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
