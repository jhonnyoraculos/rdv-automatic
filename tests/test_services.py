from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from database import Base
from exports import rdv_to_csv, rdv_to_pdf, rdv_to_xlsx
from models import BenefitType, EmployeeRole, SubmissionStatus
from services import (
    BusinessError,
    create_employee,
    create_period,
    create_rdv,
    reject_rdv,
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


def test_create_reject_and_resubmit_same_protocol() -> None:
    employee = create_employee("Maria Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 9, 1), date(2026, 9, 3), active=True)
    first = create_rdv(
        employee.id, period.id, False, 0, _entries(period.start_date, period.end_date)
    )
    reject_rdv(first.id, "Corrigir valor")
    corrected = create_rdv(
        employee.id, period.id, False, 0, _entries(period.start_date, period.end_date)
    )
    assert corrected.id == first.id
    assert corrected.status == SubmissionStatus.ENVIADO
    assert len(corrected.entries) == 3


def test_individual_exports_are_generated() -> None:
    employee = create_employee("Carlos Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 12, 1), date(2026, 12, 2), active=True)
    rdv = create_rdv(
        employee.id,
        period.id,
        False,
        0,
        _entries(period.start_date, period.end_date),
    )
    assert rdv_to_pdf(rdv).startswith(b"%PDF")
    assert rdv_to_xlsx(rdv).startswith(b"PK")
    assert rdv_to_csv(rdv).startswith(b"\xef\xbb\xbf")


def test_duplicate_sent_rdv_is_rejected() -> None:
    employee = create_employee("João Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 10, 1), date(2026, 10, 2), active=True)
    entries = _entries(period.start_date, period.end_date)
    create_rdv(employee.id, period.id, False, 0, entries)
    with pytest.raises(BusinessError, match="Já existe"):
        create_rdv(employee.id, period.id, False, 0, entries)


def test_none_requires_zero_value() -> None:
    employee = create_employee("Ana Teste", EmployeeRole.MOTORISTA)
    period = create_period(date(2026, 11, 1), date(2026, 11, 1), active=True)
    entries = _entries(period.start_date, period.end_date)
    entries[0]["benefit_type"] = BenefitType.NONE
    entries[0]["benefit_amount"] = 1
    with pytest.raises(BusinessError, match="deve ser zero"):
        create_rdv(employee.id, period.id, False, 0, entries)
