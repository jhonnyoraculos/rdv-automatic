from datetime import date
from types import SimpleNamespace

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
    delete_rdv,
    ensure_default_employees,
    get_active_period,
    get_rdv,
    reject_rdv,
    reset_employee_password,
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
    assert auth.restore_employee_login()
    assert reopened_session["employee_id"] == access.employee.id
    assert auth.current_employee_id() == access.employee.id


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

    assert rdv_to_pdf(rdv).startswith(b"%PDF")
    assert PHYSICAL_SIGNATURE_LABELS == (
        "ASSINATURA DO COLABORADOR",
        "ANALISTA DE FROTA",
        "GESTOR DE FROTA",
    )


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


def test_automatic_period_sequence_uses_requested_anchor_and_interval() -> None:
    assert get_active_period(date(2026, 9, 27)) is None

    first = get_active_period(date(2026, 9, 28))
    assert first and first.start_date == date(2026, 9, 28)
    assert first.end_date == date(2026, 10, 10)

    thursday = get_active_period(date(2026, 10, 8))
    assert thursday and thursday.id == first.id

    second = get_active_period(date(2026, 10, 9))
    assert second and second.start_date == date(2026, 10, 12)
    assert second.end_date == date(2026, 10, 24)

    third = get_active_period(date(2026, 10, 23))
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
