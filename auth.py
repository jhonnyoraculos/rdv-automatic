from __future__ import annotations

import hmac
import os

import bcrypt
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def _secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError, StreamlitSecretNotFoundError):
        return ""


def auth_configured() -> bool:
    return bool(_secret("ADMIN_USERNAME") and _secret("ADMIN_PASSWORD_HASH"))


def verify_credentials(username: str, password: str) -> bool:
    expected_user = _secret("ADMIN_USERNAME")
    password_hash = _secret("ADMIN_PASSWORD_HASH")
    if not expected_user or not password_hash:
        return False
    try:
        user_ok = hmac.compare_digest(username.strip(), expected_user)
        password_ok = bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
        return user_ok and password_ok
    except (ValueError, TypeError):
        return False


def is_authenticated() -> bool:
    return bool(st.session_state.get("admin_authenticated", False))


def login(username: str, password: str) -> bool:
    authenticated = verify_credentials(username, password)
    if authenticated:
        st.session_state["admin_authenticated"] = True
        st.session_state["admin_username"] = username.strip()
    return authenticated


def logout() -> None:
    for key in ("admin_authenticated", "admin_username", "selected_rdv_id"):
        st.session_state.pop(key, None)


def generate_password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres.")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
