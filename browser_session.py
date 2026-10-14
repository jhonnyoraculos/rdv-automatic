from __future__ import annotations

import streamlit as st

COOKIE_NAME = "rdv_employee_session"
COOKIE_MAX_AGE_SECONDS = 90 * 24 * 60 * 60

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


def save_employee_cookie(token: str) -> None:
    _cookie_control(
        data={
            "action": "save",
            "name": COOKIE_NAME,
            "value": token,
            "maxAge": COOKIE_MAX_AGE_SECONDS,
        },
        key="save_employee_cookie",
        on_token_change=lambda: None,
        on_completed_change=lambda: None,
    )


def load_employee_browser_token() -> str:
    result = _cookie_control(
        data={
            "action": "read",
            "name": COOKIE_NAME,
            "value": "",
            "maxAge": COOKIE_MAX_AGE_SECONDS,
        },
        key="read_employee_cookie",
        on_token_change=lambda: None,
        on_completed_change=lambda: None,
    )
    return str(getattr(result, "token", "") or "").strip()


def clear_employee_cookie() -> None:
    _cookie_control(
        data={"action": "clear", "name": COOKIE_NAME, "value": "", "maxAge": 0},
        key="clear_employee_cookie",
        on_token_change=lambda: None,
        on_completed_change=lambda: None,
    )
