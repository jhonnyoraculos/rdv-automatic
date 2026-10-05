from __future__ import annotations

import hmac
import os
from enum import Enum

import bcrypt
import streamlit as st
from sqlalchemy import func, select
from streamlit.errors import StreamlitSecretNotFoundError

from database import session_scope
from models import Employee


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
        employee_id = employee.id
        employee_name = employee.name
    st.session_state["employee_authenticated"] = True
    st.session_state["employee_id"] = employee_id
    st.session_state["employee_name"] = employee_name
    return True


def logout() -> None:
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
    ):
        st.session_state.pop(key, None)


def generate_password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
