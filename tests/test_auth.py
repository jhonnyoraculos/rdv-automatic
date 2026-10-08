import auth
import browser_session
from auth import (
    AdminRole,
    generate_password_hash,
    switch_admin_role,
    verify_credentials,
)


def test_employee_cookie_triggers_streamlit_without_reloading_browser(
    monkeypatch,
) -> None:
    mounted = {}
    monkeypatch.setattr(
        browser_session,
        "_cookie_control",
        lambda **kwargs: mounted.update(kwargs),
    )

    browser_session.save_employee_cookie("temporary-token")

    assert mounted["data"]["action"] == "save"
    assert mounted["data"]["value"] == "temporary-token"
    assert callable(mounted["on_completed_change"])
    assert "window.location.reload" not in browser_session.COOKIE_JS
    assert 'setTriggerValue("completed"' in browser_session.COOKIE_JS


def test_legacy_password_creates_analyst_and_manager_accounts(monkeypatch) -> None:
    password_hash = generate_password_hash("senha-segura")
    values = {
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD_HASH": password_hash,
    }
    monkeypatch.setattr(auth, "_secret", lambda name: values.get(name, ""))

    assert verify_credentials("analista", "senha-segura") == AdminRole.ANALISTA
    assert verify_credentials("gestor", "senha-segura") == AdminRole.GESTOR
    assert verify_credentials("admin", "senha-segura") == AdminRole.ANALISTA
    assert verify_credentials("gestor", "incorreta") is None


def test_authenticated_user_can_switch_test_role(monkeypatch) -> None:
    session = {
        "admin_authenticated": True,
        "admin_role": AdminRole.ANALISTA.value,
        "opened_rdv_id": 12,
    }
    monkeypatch.setattr(auth.st, "session_state", session)

    assert switch_admin_role(AdminRole.GESTOR) == AdminRole.GESTOR
    assert session["admin_role"] == AdminRole.GESTOR.value
    assert "opened_rdv_id" not in session
