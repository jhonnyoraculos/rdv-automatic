import auth
from auth import AdminRole, generate_password_hash, verify_credentials


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
