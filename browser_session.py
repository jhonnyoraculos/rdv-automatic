from __future__ import annotations

import streamlit as st

COOKIE_NAME = "rdv_employee_session"
COOKIE_MAX_AGE_SECONDS = 90 * 24 * 60 * 60

COOKIE_HTML = '<div class="rdv-cookie-control"></div>'
COOKIE_JS = """
export default function({ parentElement, data }) {
    const marker = parentElement.querySelector('.rdv-cookie-control');
    const operation = `${data.action}:${data.value || ''}`;
    if (marker.dataset.operation === operation) return;
    marker.dataset.operation = operation;
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    const value = data.action === "save" ? encodeURIComponent(data.value) : "";
    const maxAge = data.action === "save" ? data.maxAge : 0;
    document.cookie = data.name + "=" + value + "; Path=/; Max-Age=" + maxAge
        + "; SameSite=Lax" + secure;
    setTimeout(() => window.location.reload(), 100);
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
    )


def clear_employee_cookie() -> None:
    _cookie_control(
        data={"action": "clear", "name": COOKIE_NAME, "value": "", "maxAge": 0},
        key="clear_employee_cookie",
    )
