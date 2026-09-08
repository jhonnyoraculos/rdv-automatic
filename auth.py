from __future__ import annotations

import hmac
import os
from enum import Enum

import bcrypt
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


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


def current_admin_role() -> AdminRole | None:
    if not is_authenticated():
        return None
    try:
        return AdminRole(st.session_state.get("admin_role", AdminRole.ANALISTA.value))
    except ValueError:
        return None


def current_admin_username() -> str:
    return str(st.session_state.get("admin_username", "")).strip()


def login(username: str, password: str) -> bool:
    role = verify_credentials(username, password)
    if role:
        st.session_state["admin_authenticated"] = True
        st.session_state["admin_username"] = username.strip()
        st.session_state["admin_role"] = role.value
        return True
    return False


def logout() -> None:
    for key in (
        "admin_authenticated",
        "admin_username",
        "admin_role",
        "selected_rdv_id",
        "opened_rdv_id",
    ):
        st.session_state.pop(key, None)


def generate_password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
