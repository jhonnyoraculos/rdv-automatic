from datetime import date
from types import SimpleNamespace

import pypdfium2 as pdfium
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import auth
import database
from database import Base
from exports import (
    PHYSICAL_SIGNATURE_LABELS,
    rdv_to_csv,
    rdv_to_pdf,
    rdv_to_png,
    rdv_to_xlsx,
)
from models import BenefitType, Employee, EmployeeRole, SubmissionStatus
from services import (
    DEFAULT_EMPLOYEES,
    BusinessError,
    approve_rdv,
    create_employee,
    create_employee_with_access,
    create_period,
    create_rdv,
    dashboard_stats,
    delete_rdv,
    ensure_default_employees,
    get_active_period,
    get_expense_settings,
    get_rdv,
    get_rdvs,
    get_submission_for_employee_period,
    reject_rdv,
    reopen_rdv_for_editing,
    reset_employee_password,
    save_rdv_draft,
    set_employee_password,
    update_employee,
    update_expense_settings,
)
from utils import date_range


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False)
    )
    yield
    engine.dispose()


def _entries(start: date, end: date):
    return [
        {
            "date": day,
            "city": "Bauru",
            "hotel_name": "",
            "hotel_amount": 0,
            "benefit_type": BenefitType.DIARIA if day == start else BenefitType.NONE,
            "benefit_amount": 100 if day == start else 0,
        }
        for day in date_range(start, end)
    ]


def _create_test_rdv(employee_id: int, period_id: int, entries):
    return create_rdv(
        employee_id,
        period_id,
        False,
        0,
        entries,
        "Bauru/SP",
    )


def test_employee_access_is_generated_hashed_and_identifies_employee(monkeypatch) -> None:
    access = create_employee_with_access("Maria da Silva", EmployeeRole.MOTORISTA)

    assert access.username == "maria.da.silva"
    assert access.temporary_password not in access.employee.password_hash
    session_state = {}
    monkeypatch.setattr(auth.st, "session_state", session_state)
    assert auth.login_employee(access.username, access.temporary_password)
    assert session_state["employee_id"] == access.employee.id


def test_employee_login_is_restored_from_persistent_token(monkeypatch) -> None:
    access = create_employee_with_access("Login Persistente", EmployeeRole.MOTORISTA)
    first_session = {}
    monkeypatch.setattr(auth.st, "session_state", first_session)
    monkeypatch.setattr(auth.st, "context", SimpleNamespace(cookies={}))

    assert auth.login_employee(access.username, access.temporary_password)
    token = auth.consume_new_employee_token()
    assert token

    reopened_session = {}
    monkeypatch.setattr(auth.st, "session_state", reopened_session)
    monkeypatch.setattr(
        auth.st,
        "context",
        SimpleNamespace(cookies={"rdv_employee_session": token}),
    )
    assert auth.restore_employee_login(token)
    assert reopened_session["employee_id"] == access.employee.id
    assert auth.current_employee_id() == access.employee.id


def test_admin_login_is_restored_from_saved_device_token(monkeypatch) -> None:
    password_hash = auth.generate_password_hash("senha-segura")
    values = {
        "ANALYST_USERNAME": "analista",
        "ANALYST_PASSWORD_HASH": password_hash,
    }
    monkeypatch.setattr(auth, "_secret", lambda name: values.get(name, ""))
    monkeypatch.setattr(auth.st, "session_state", {})
    monkeypatch.setattr(auth.st, "context", SimpleNamespace(cookies={}))

    assert auth.login("analista", "senha-segura")
    token = auth.consume_new_admin_token()
    assert token

    reopened_session = {}
    monkeypatch.setattr(auth.st, "session_state", reopened_session)
    monkeypatch.setattr(
        auth.st,
        "context",
        SimpleNamespace(cookies={"rdv_admin_session": token}),
    )
    assert auth.restore_admin_login(token)
    assert reopened_session["admin_username"] == "analista"
    assert reopened_session["admin_role"] == auth.AdminRole.ANALISTA.value


def test_new_password_revokes_saved_logins(monkeypatch) -> None:
    access = create_employee_with_access("Sessão Revogada", EmployeeRole.AJUDANTE)
    monkeypatch.setattr(auth.st, "session_state", {})
    monkeypatch.setattr(auth.st, "context", SimpleNamespace(cookies={}))
    assert auth.login_employee(access.username, access.temporary_password)
    token = auth.consume_new_employee_token()

    reset_employee_password(access.employee.id)
    monkeypatch.setattr(auth.st, "session_state", {})
    monkeypatch.setattr(
        auth.st,
        "context",
        SimpleNamespace(cookies={"rdv_employee_session": token}),
    )
    assert not auth.restore_employee_login()


def test_reset_password_invalidates_previous_password(monkeypatch) -> None:
    access = create_employee_with_access("Paulo Teste", EmployeeRole.AJUDANTE)
    renewed = reset_employee_password(access.employee.id)
    monkeypatch.setattr(auth.st, "session_state", {})

    assert not auth.login_employee(access.username, access.temporary_password)
    assert auth.login_employee(renewed.username, renewed.temporary_password)


def test_admin_defined_password_remains_valid_until_manual_change(monkeypatch) -> None:
    access = create_employee_with_access(
        "Senha Fixa",
        EmployeeRole.MOTORISTA,
        password="minha-senha-fixa",
    )
    monkeypatch.setattr(auth.st, "session_state", {})

    assert auth.login_employee(access.username, "minha-senha-fixa")

    update_employee(access.employee.id, "Senha Fixa", EmployeeRole.MOTORISTA, True)
    monkeypatch.setattr(auth.st, "session_state", {})
    assert auth.login_employee(access.username, " minha-senha-fixa ")

    set_employee_password(access.employee.id, "nova-senha-fixa")
    monkeypatch.setattr(auth.st, "session_state", {})
    assert not auth.login_employee(access.username, "minha-senha-fixa")
    assert auth.login_employee(access.username, "nova-senha-fixa")


def test_admin_can_change_employee_login_username(monkeypatch) -> None:
    access = create_employee_with_access(
        "Usuário Editável",
        EmployeeRole.AJUDANTE,
        password="senha-fixa-teste",
    )
    other = create_employee_with_access(
        "Outro Usuário",
        EmployeeRole.MOTORISTA,
        password="outra-senha-fixa",
    )
    previous_username = access.username

    updated = update_employee(
        access.employee.id,
        access.employee.name,
        access.employee.role,
        True,
        username="novo.login_01",
    )

    assert updated.username == "novo.login_01"
    monkeypatch.setattr(auth.st, "session_state", {})
    assert not auth.login_employee(previous_username, "senha-fixa-teste")
    assert auth.login_employee("NOVO.LOGIN_01", "senha-fixa-teste")

    updated_with_space = update_employee(
        access.employee.id,
        access.employee.name,
        access.employee.role,
        True,
        username="marco veiga",
    )
    assert updated_with_space.username == "marco veiga"
    monkeypatch.setattr(auth.st, "session_state", {})
    assert auth.login_employee("marco veiga", "senha-fixa-teste")

    with pytest.raises(BusinessError, match="já está em uso"):
        update_employee(
            other.employee.id,
            other.employee.name,
            other.employee.role,
            True,
            username="marco veiga",
        )
    with pytest.raises(BusinessError, match="somente letras"):
        update_employee(
            access.employee.id,
            access.employee.name,
            access.employee.role,
            True,
            username="login@invalido",
        )


def test_create_reject_and_resubmit_same_protocol() -> None:
    employee = create_employee("Maria Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 3), active=True)
    first = _create_test_rdv(
        employee.id, period.id, _entries(period.start_date, period.end_date)
    )
    reject_rdv(first.id, "Corrigir valor")
    corrected = _create_test_rdv(
        employee.id, period.id, _entries(period.start_date, period.end_date)
    )
    assert corrected.id == first.id
    assert corrected.status == SubmissionStatus.ENVIADO
    assert len(corrected.entries) == 3


def test_partial_draft_is_saved_resumed_and_hidden_from_admin() -> None:
    employee = create_employee("Rascunho Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 3), active=True)
    entries = _entries(period.start_date, period.end_date)
    entries[0]["city"] = ""
    entries[0]["benefit_amount"] = 0

    draft = save_rdv_draft(
        employee.id,
        period.id,
        True,
        0,
        entries,
        "",
    )

    assert draft.status == SubmissionStatus.RASCUNHO
    assert draft.location == ""
    assert draft.advance_amount == 0
    assert get_rdvs() == []
    assert dashboard_stats()["total"] == 0
    resumed = get_submission_for_employee_period(employee.id, period.id)
    assert resumed and resumed.id == draft.id
    assert len(resumed.entries) == 3


def test_draft_updates_same_record_and_only_locks_after_submission() -> None:
    employee = create_employee("Envio de Rascunho", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 2), active=True)
    partial = _entries(period.start_date, period.end_date)
    partial[0]["benefit_amount"] = 0
    first = save_rdv_draft(
        employee.id, period.id, False, 0, partial, "Divinópolis/MG"
    )

    partial[0]["city"] = "Itaúna"
    second = save_rdv_draft(
        employee.id, period.id, False, 0, partial, "Divinópolis/MG"
    )
    assert second.id == first.id
    assert second.status == SubmissionStatus.RASCUNHO

    final_entries = _entries(period.start_date, period.end_date)
    sent = create_rdv(
        employee.id,
        period.id,
        False,
        0,
        final_entries,
        "Divinópolis/MG",
    )
    assert sent.id == first.id
    assert sent.status == SubmissionStatus.ENVIADO
    assert len(get_rdvs()) == 1

    with pytest.raises(BusinessError, match="não pode mais ser alterado"):
        save_rdv_draft(
            employee.id, period.id, False, 0, partial, "Divinópolis/MG"
        )


def test_admin_configures_fixed_benefit_values_enforced_by_server() -> None:
    defaults = get_expense_settings()
    assert defaults.daily_amount == 100
    assert defaults.ticket_amount == 32

    configured = update_expense_settings(125.50, 40, "analista")
    assert configured.daily_amount == 125.50
    assert configured.ticket_amount == 40
    assert configured.updated_by == "analista"

    employee = create_employee("Valores Fixos", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 2), active=True)
    entries = _entries(period.start_date, period.end_date)
    entries[0]["benefit_amount"] = 999
    entries[1]["benefit_type"] = BenefitType.TICKET
    entries[1]["benefit_amount"] = 999

    rdv = create_rdv(
        employee.id,
        period.id,
        False,
        0,
        entries,
        "Divinópolis/MG",
    )

    amounts = {entry.benefit_type: entry.benefit_amount for entry in rdv.entries}
    assert amounts[BenefitType.DIARIA] == 125.50
    assert amounts[BenefitType.TICKET] == 40


def test_fixed_benefit_values_must_be_positive() -> None:
    with pytest.raises(BusinessError, match="diária deve ser maior"):
        update_expense_settings(0, 32, "analista")


def test_individual_exports_are_generated() -> None:
    employee = create_employee("Carlos Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 12, 1), date(2026, 12, 2), active=True)
    rdv = _create_test_rdv(
        employee.id,
        period.id,
        _entries(period.start_date, period.end_date),
    )
    assert rdv_to_pdf(rdv).startswith(b"%PDF")
    assert rdv_to_png(rdv).startswith(b"\x89PNG")
    assert rdv_to_xlsx(rdv).startswith(b"PK")
    assert rdv_to_csv(rdv).startswith(b"\xef\xbb\xbf")


def test_duplicate_sent_rdv_is_rejected() -> None:
    employee = create_employee("João Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 10, 1), date(2026, 10, 2), active=True)
    entries = _entries(period.start_date, period.end_date)
    _create_test_rdv(employee.id, period.id, entries)
    with pytest.raises(BusinessError, match="Já existe"):
        _create_test_rdv(employee.id, period.id, entries)


def test_none_requires_zero_value() -> None:
    employee = create_employee("Ana Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 11, 1), date(2026, 11, 1), active=True)
    entries = _entries(period.start_date, period.end_date)
    entries[0]["benefit_type"] = BenefitType.NONE
    entries[0]["benefit_amount"] = 1
    with pytest.raises(BusinessError, match="deve ser zero"):
        _create_test_rdv(employee.id, period.id, entries)


def test_location_is_required() -> None:
    employee = create_employee("Bia Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)
    entries = _entries(period.start_date, period.end_date)
    with pytest.raises(BusinessError, match="Local é obrigatório"):
        create_rdv(
            employee.id,
            period.id,
            False,
            0,
            entries,
            "",
        )


def test_pdf_is_generated_with_physical_signature_lines() -> None:
    employee = create_employee("Caio Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)

    rdv = create_rdv(
        employee.id,
        period.id,
        False,
        0,
        _entries(period.start_date, period.end_date),
        "Bauru/SP",
    )

    pdf_data = rdv_to_pdf(rdv)
    assert pdf_data.startswith(b"%PDF")
    assert PHYSICAL_SIGNATURE_LABELS == (
        "ASSINATURA DO COLABORADOR",
        "ANALISTA DE FROTA",
        "GESTOR DE FROTA",
    )
    document = pdfium.PdfDocument(pdf_data)
    try:
        page = document[0]
        try:
            text_page = page.get_textpage()
            try:
                pdf_text = text_page.get_text_range()
            finally:
                text_page.close()
        finally:
            page.close()
    finally:
        document.close()
    for label in PHYSICAL_SIGNATURE_LABELS:
        assert label in pdf_text


def test_analyst_approval_concludes_the_rdv() -> None:
    employee = create_employee("Rui Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)
    rdv = _create_test_rdv(
        employee.id, period.id, _entries(period.start_date, period.end_date)
    )

    approved = approve_rdv(rdv.id, "ANALISTA", "analista")
    assert approved.status == SubmissionStatus.APROVADO
    assert approved.analyst_signed_at
    assert approved.analyst_username == "analista"
    assert approved.manager_signed_at is None
    assert approved.manager_username is None
    assert rdv_to_pdf(approved).startswith(b"%PDF")


def test_only_analyst_can_approve() -> None:
    employee = create_employee("Eva Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)
    rdv = _create_test_rdv(
        employee.id, period.id, _entries(period.start_date, period.end_date)
    )
    with pytest.raises(BusinessError, match="analista"):
        approve_rdv(rdv.id, "GESTOR", "gestor")


def test_analyst_rejection_restarts_the_approval_flow() -> None:
    employee = create_employee("Leo Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)
    entries = _entries(period.start_date, period.end_date)
    rdv = _create_test_rdv(employee.id, period.id, entries)
    rejected = reject_rdv(rdv.id, "Corrigir cidade", "ANALISTA")
    assert rejected.status == SubmissionStatus.REJEITADO
    corrected = _create_test_rdv(employee.id, period.id, entries)
    assert corrected.status == SubmissionStatus.ENVIADO
    assert corrected.analyst_signed_at is None
    assert corrected.manager_signed_at is None


def test_admin_can_delete_rdv_so_employee_can_submit_again() -> None:
    employee = create_employee("Nina Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)
    entries = _entries(period.start_date, period.end_date)
    rdv = _create_test_rdv(employee.id, period.id, entries)

    delete_rdv(rdv.id, "ANALISTA", "analista")

    assert get_rdv(rdv.id) is None
    replacement = _create_test_rdv(employee.id, period.id, entries)
    assert replacement.status == SubmissionStatus.ENVIADO


def test_sent_or_approved_rdv_can_be_reopened_edited_and_resent() -> None:
    employee = create_employee("Edição Após Envio", EmployeeRole.MOTORISTA)
    other_employee = create_employee("Outro Colaborador", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 1), active=True)
    entries = _entries(period.start_date, period.end_date)
    sent = _create_test_rdv(employee.id, period.id, entries)
    approved = approve_rdv(sent.id, "ANALISTA", "analista")

    with pytest.raises(BusinessError, match="outro colaborador"):
        reopen_rdv_for_editing(approved.id, employee_id=other_employee.id)

    reopened = reopen_rdv_for_editing(approved.id, employee_id=employee.id)
    assert reopened.status == SubmissionStatus.RASCUNHO
    assert reopened.analyst_signed_at is None
    assert reopened.analyst_username is None

    entries[0]["city"] = "Cidade corrigida"
    resent = _create_test_rdv(employee.id, period.id, entries)
    assert resent.id == approved.id
    assert resent.status == SubmissionStatus.ENVIADO
    assert resent.entries[0].city == "Cidade corrigida"


def test_automatic_period_sequence_uses_requested_anchor_and_interval() -> None:
    assert get_active_period(date(2026, 9, 27)) is None

    first = get_active_period(date(2026, 9, 28))
    assert first and first.start_date == date(2026, 9, 28)
    assert first.end_date == date(2026, 10, 10)

    thursday = get_active_period(date(2026, 10, 8))
    assert thursday and thursday.id == first.id

    friday = get_active_period(date(2026, 10, 9))
    assert friday and friday.id == first.id

    sunday = get_active_period(date(2026, 10, 11))
    assert sunday and sunday.id == first.id

    second = get_active_period(date(2026, 10, 12))
    assert second and second.start_date == date(2026, 10, 12)
    assert second.end_date == date(2026, 10, 24)

    friday_before_third = get_active_period(date(2026, 10, 23))
    assert friday_before_third and friday_before_third.id == second.id

    third = get_active_period(date(2026, 10, 26))
    assert third and third.start_date == date(2026, 10, 26)
    assert third.end_date == date(2026, 11, 7)


def test_supplied_employees_are_seeded_once_with_their_roles() -> None:
    assert ensure_default_employees() == len(DEFAULT_EMPLOYEES) == 50
    assert ensure_default_employees() == 0

    with database.session_scope() as session:
        employees = list(session.query(Employee).order_by(Employee.name))

    assert len(employees) == 50
    assert sum(item.role == EmployeeRole.MOTORISTA for item in employees) == 26
    assert sum(item.role == EmployeeRole.AJUDANTE for item in employees) == 24
    assert all(item.password_hash is None for item in employees)
    roles = {item.name: item.role for item in employees}
    assert roles["ROBERT JHONATHAN SILVA"] == EmployeeRole.MOTORISTA
    assert roles["MARCO VINICIO ALMEIDA VEIGA"] == EmployeeRole.AJUDANTE
