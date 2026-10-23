from __future__ import annotations

import streamlit as st

COOKIE_NAME = "rdv_employee_session"
ADMIN_COOKIE_NAME = "rdv_admin_session"
COOKIE_MAX_AGE_DAYS = 365
COOKIE_MAX_AGE_SECONDS = COOKIE_MAX_AGE_DAYS * 24 * 60 * 60

COOKIE_HTML = '<div class="rdv-cookie-control"></div>'
COOKIE_JS = """
export default function({ parentElement, data, setStateValue, setTriggerValue }) {
    const marker = parentElement.querySelector('.rdv-cookie-control');
    const operation = `${data.action}:${data.value || ''}`;
    if (marker.dataset.operation === operation) return;
    marker.dataset.operation = operation;

    let storage = window.localStorage;
    let cookieDocument = document;
    try {
        if (window.parent && window.parent !== window) {
            storage = window.parent.localStorage;
            cookieDocument = window.parent.document;
        }
    } catch (_) {
        // Cross-origin embedding: the component's own storage remains usable.
    }

    let storedToken = "";
    try {
        if (data.action === "save") {
            storage.setItem(data.name, data.value);
        } else if (data.action === "clear") {
            storage.removeItem(data.name);
        }
        storedToken = storage.getItem(data.name) || "";
    } catch (_) {
        // Cookies below remain as a fallback if storage is unavailable.
    }

    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    const value = data.action === "save" ? encodeURIComponent(data.value) : "";
    const maxAge = data.action === "save" ? data.maxAge : 0;
    if (data.action !== "read") {
        cookieDocument.cookie = data.name + "=" + value + "; Path=/; Max-Age=" + maxAge
        + "; SameSite=Lax" + secure;
    }
    if (!storedToken && data.action !== "clear") {
        const prefix = data.name + "=";
        const cookie = cookieDocument.cookie
            .split("; ")
            .find((item) => item.startsWith(prefix));
        if (cookie) storedToken = decodeURIComponent(cookie.slice(prefix.length));
    }
    setStateValue("token", storedToken);
    setTriggerValue("completed", operation);
}
"""

_cookie_control = st.components.v2.component(
    "rdv_persistent_login_cookie",
    html=COOKIE_HTML,
    js=COOKIE_JS,
)


def _save_browser_token(token: str, name: str, key: str) -> None:
    _cookie_control(
        data={
            "action": "save",
            "name": name,
            "value": token,
            "maxAge": COOKIE_MAX_AGE_SECONDS,
        },
        key=key,
        on_token_change=lambda: None,
        on_completed_change=lambda: None,
    )


def _load_browser_token(name: str, key: str) -> str:
    result = _cookie_control(
        data={
            "action": "read",
            "name": name,
            "value": "",
            "maxAge": COOKIE_MAX_AGE_SECONDS,
        },
        key=key,
        on_token_change=lambda: None,
        on_completed_change=lambda: None,
    )
    return str(getattr(result, "token", "") or "").strip()


def _clear_browser_token(name: str, key: str) -> None:
    _cookie_control(
        data={"action": "clear", "name": name, "value": "", "maxAge": 0},
        key=key,
        on_token_change=lambda: None,
        on_completed_change=lambda: None,
    )


def save_employee_cookie(token: str) -> None:
    _save_browser_token(token, COOKIE_NAME, "save_employee_cookie")


def load_employee_browser_token() -> str:
    return _load_browser_token(COOKIE_NAME, "read_employee_cookie")


def clear_employee_cookie() -> None:
    _clear_browser_token(COOKIE_NAME, "clear_employee_cookie")


def save_admin_cookie(token: str) -> None:
    _save_browser_token(token, ADMIN_COOKIE_NAME, "save_admin_cookie")


def load_admin_browser_token() -> str:
    return _load_browser_token(ADMIN_COOKIE_NAME, "read_admin_cookie")


def clear_admin_cookie() -> None:
    _clear_browser_token(ADMIN_COOKIE_NAME, "clear_admin_cookie")
