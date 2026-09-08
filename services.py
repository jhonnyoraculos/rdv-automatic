from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from database import session_scope
from models import (
    BenefitType,
    Employee,
    EmployeeRole,
    RdvEntry,
    RdvPeriod,
    RdvSubmission,
    SubmissionStatus,
)
from utils import (
    calculate_rdv_totals,
    clean_text,
    date_range,
    money,
    now_sp,
    validate_signature_png,
)

logger = logging.getLogger("rdv")


class BusinessError(ValueError):
    """Safe validation error that can be displayed in the interface."""


def _role(value: EmployeeRole | str) -> EmployeeRole:
    try:
        return value if isinstance(value, EmployeeRole) else EmployeeRole(str(value))
    except ValueError as exc:
        raise BusinessError("Função do colaborador inválida.") from exc


def _benefit(value: BenefitType | str) -> BenefitType:
    try:
        return value if isinstance(value, BenefitType) else BenefitType(str(value))
    except ValueError as exc:
        raise BusinessError("Tipo de benefício inválido.") from exc


def create_employee(
    name: str, role: EmployeeRole | str, active: bool = True
) -> Employee:
    normalized_name = clean_text(name, "Nome", 150, required=True).upper()
    timestamp = now_sp()
    with session_scope() as session:
        duplicate = session.scalar(
            select(Employee).where(func.lower(Employee.name) == normalized_name.lower())
        )
        if duplicate:
            raise BusinessError("Já existe um colaborador com esse nome.")
        employee = Employee(
            name=normalized_name,
            role=_role(role),
            active=bool(active),
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(employee)
        session.flush()
        logger.info("Colaborador criado: id=%s nome=%s", employee.id, employee.name)
        return employee


def update_employee(
    employee_id: int, name: str, role: EmployeeRole | str, active: bool
) -> Employee:
    normalized_name = clean_text(name, "Nome", 150, required=True).upper()
    with session_scope() as session:
        employee = session.get(Employee, employee_id)
        if not employee:
            raise BusinessError("Colaborador não encontrado.")
        duplicate = session.scalar(
            select(Employee).where(
                func.lower(Employee.name) == normalized_name.lower(),
                Employee.id != employee_id,
            )
        )
        if duplicate:
            raise BusinessError("Já existe outro colaborador com esse nome.")
        employee.name = normalized_name
        employee.role = _role(role)
        employee.active = bool(active)
        employee.updated_at = now_sp()
        session.flush()
        logger.info("Colaborador alterado: id=%s", employee.id)
        return employee


def get_employee(employee_id: int) -> Employee | None:
    with session_scope() as session:
        return session.get(Employee, employee_id)


def get_employees(search: str = "", active_only: bool = False) -> list[Employee]:
    with session_scope() as session:
        statement = select(Employee)
        if active_only:
            statement = statement.where(Employee.active.is_(True))
        if search.strip():
            statement = statement.where(Employee.name.ilike(f"%{search.strip()}%"))
        return list(session.scalars(statement.order_by(Employee.name)))


def get_active_employees() -> list[Employee]:
    return get_employees(active_only=True)


def _deactivate_periods(session: Any, except_id: int | None = None) -> None:
    statement = select(RdvPeriod).where(RdvPeriod.active.is_(True))
    if except_id is not None:
        statement = statement.where(RdvPeriod.id != except_id)
    for period in session.scalars(statement):
        period.active = False


def create_period(
    start_date: date, end_date: date, description: str = "", active: bool = False
) -> RdvPeriod:
    if end_date < start_date:
        raise BusinessError("A data final deve ser igual ou posterior à inicial.")
    if (end_date - start_date).days > 45:
        raise BusinessError("O período não pode ultrapassar 46 dias.")
    description = clean_text(description, "Descrição", 150)
    with session_scope() as session:
        duplicate = session.scalar(
            select(RdvPeriod).where(
                RdvPeriod.start_date == start_date, RdvPeriod.end_date == end_date
            )
        )
        if duplicate:
            raise BusinessError("Já existe um período com essas datas.")
        if active:
            _deactivate_periods(session)
            session.flush()
        period = RdvPeriod(
            start_date=start_date,
            end_date=end_date,
            description=description,
            active=bool(active),
            created_at=now_sp(),
        )
        session.add(period)
        session.flush()
        logger.info("Período criado: id=%s", period.id)
        return period


def update_period(
    period_id: int, start_date: date, end_date: date, description: str, active: bool
) -> RdvPeriod:
    if end_date < start_date:
        raise BusinessError("A data final deve ser igual ou posterior à inicial.")
    if (end_date - start_date).days > 45:
        raise BusinessError("O período não pode ultrapassar 46 dias.")
    with session_scope() as session:
        period = session.get(RdvPeriod, period_id)
        if not period:
            raise BusinessError("Período não encontrado.")
        has_submissions = session.scalar(
            select(func.count(RdvSubmission.id)).where(
                RdvSubmission.period_id == period_id
            )
        )
        if has_submissions and (
            period.start_date != start_date or period.end_date != end_date
        ):
            raise BusinessError(
                "As datas de um período com RDVs não podem ser alteradas."
            )
        if active:
            _deactivate_periods(session, except_id=period_id)
            session.flush()
        period.start_date = start_date
        period.end_date = end_date
        period.description = clean_text(description, "Descrição", 150)
        period.active = bool(active)
        session.flush()
        logger.info("Período alterado: id=%s ativo=%s", period.id, period.active)
        return period


def get_periods() -> list[RdvPeriod]:
    with session_scope() as session:
        return list(
            session.scalars(select(RdvPeriod).order_by(RdvPeriod.start_date.desc()))
        )


def get_active_period() -> RdvPeriod | None:
    with session_scope() as session:
        return session.scalar(
            select(RdvPeriod)
            .where(RdvPeriod.active.is_(True))
            .order_by(RdvPeriod.created_at.desc())
        )


def get_period(period_id: int) -> RdvPeriod | None:
    with session_scope() as session:
        return session.get(RdvPeriod, period_id)


def validate_rdv_payload(
    employee: Employee,
    period: RdvPeriod,
    advance_received: bool,
    advance_amount: Any,
    entries: Iterable[dict[str, Any]],
) -> tuple[Decimal, list[dict[str, Any]]]:
    advance = money(advance_amount, "Valor do adiantamento")
    if advance_received and advance <= 0:
        raise BusinessError("Informe um adiantamento maior que zero.")
    if not advance_received and advance != 0:
        raise BusinessError(
            "O adiantamento deve ser zero quando a opção selecionada é Não."
        )

    normalized: list[dict[str, Any]] = []
    seen_dates: set[date] = set()
    for raw in entries:
        entry_date = raw.get("date")
        if (
            not isinstance(entry_date, date)
            or not period.start_date <= entry_date <= period.end_date
        ):
            raise BusinessError(
                "Foi encontrado um lançamento fora do período selecionado."
            )
        if entry_date in seen_dates:
            raise BusinessError("Não é permitido repetir uma data no mesmo RDV.")
        seen_dates.add(entry_date)
        city = clean_text(raw.get("city"), "Cidade", 120)
        hotel_name = clean_text(raw.get("hotel_name"), "Hotel", 150)
        hotel_amount = money(raw.get("hotel_amount", 0), "Valor do hotel")
        benefit_type = _benefit(raw.get("benefit_type", BenefitType.NONE))
        benefit_amount = money(raw.get("benefit_amount", 0), "Valor da diária/ticket")

        if employee.role == EmployeeRole.MOTORISTA and (hotel_name or hotel_amount):
            raise BusinessError(
                "Motoristas não podem lançar despesas de hotel neste formulário."
            )
        if not hotel_name and hotel_amount != 0:
            raise BusinessError(
                f"Informe o hotel referente ao valor lançado em {entry_date:%d/%m/%Y}."
            )
        if benefit_type == BenefitType.NONE and benefit_amount != 0:
            raise BusinessError(
                f"O valor deve ser zero quando o tipo é Nenhum em {entry_date:%d/%m/%Y}."
            )
        if benefit_type != BenefitType.NONE and benefit_amount <= 0:
            raise BusinessError(f"Informe o valor da despesa de {entry_date:%d/%m/%Y}.")
        normalized.append(
            {
                "date": entry_date,
                "city": city,
                "hotel_name": hotel_name,
                "hotel_amount": hotel_amount,
                "benefit_type": benefit_type,
                "benefit_amount": benefit_amount,
            }
        )
    expected = set(date_range(period.start_date, period.end_date))
    if seen_dates != expected:
        raise BusinessError(
            "O relatório deve conter exatamente todas as datas do período."
        )
    return advance, normalized


def create_rdv(
    employee_id: int,
    period_id: int,
    advance_received: bool,
    advance_amount: Any,
    entries: Iterable[dict[str, Any]],
    location: str,
    signed_date: date,
    signature_data: bytes,
) -> RdvSubmission:
    try:
        try:
            normalized_location = clean_text(
                location, "Local", 80, required=True
            ).upper()
            normalized_signature = validate_signature_png(signature_data)
        except ValueError as exc:
            raise BusinessError(str(exc)) from exc
        if not isinstance(signed_date, date):
            raise BusinessError("Informe a data da assinatura.")

        with session_scope() as session:
            employee = session.get(Employee, employee_id)
            period = session.get(RdvPeriod, period_id)
            if not employee or not employee.active:
                raise BusinessError("Colaborador não encontrado ou inativo.")
            if not period:
                raise BusinessError("Período não encontrado.")
            advance, normalized = validate_rdv_payload(
                employee, period, advance_received, advance_amount, entries
            )
            existing = session.scalar(
                select(RdvSubmission)
                .options(selectinload(RdvSubmission.entries))
                .where(
                    RdvSubmission.employee_id == employee_id,
                    RdvSubmission.period_id == period_id,
                )
            )
            timestamp = now_sp()
            if existing and existing.status != SubmissionStatus.REJEITADO:
                raise BusinessError(
                    "Já existe um RDV enviado para este colaborador neste período."
                )
            if existing:
                submission = existing
                submission.entries.clear()
                # Deletes must reach the database before rows with the same
                # submission/date unique key are inserted again.
                session.flush()
                submission.advance_received = bool(advance_received)
                submission.advance_amount = advance
                submission.location = normalized_location
                submission.signed_date = signed_date
                submission.signature_data = normalized_signature
                submission.status = SubmissionStatus.ENVIADO
                submission.submitted_at = timestamp
                submission.reviewed_at = None
                submission.admin_comment = None
                submission.updated_at = timestamp
            else:
                submission = RdvSubmission(
                    employee_id=employee_id,
                    period_id=period_id,
                    advance_received=bool(advance_received),
                    advance_amount=advance,
                    location=normalized_location,
                    signed_date=signed_date,
                    signature_data=normalized_signature,
                    status=SubmissionStatus.ENVIADO,
                    submitted_at=timestamp,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                session.add(submission)
                session.flush()
            for item in normalized:
                submission.entries.append(RdvEntry(**item, created_at=timestamp))
            session.flush()
            submission_id = submission.id
            logger.info(
                "RDV enviado: id=%s colaborador=%s período=%s",
                submission_id,
                employee_id,
                period_id,
            )
        loaded = get_rdv(submission_id)
        if not loaded:
            raise RuntimeError("Falha ao recuperar o RDV salvo.")
        return loaded
    except IntegrityError as exc:
        raise BusinessError(
            "Já existe um RDV enviado para este colaborador neste período."
        ) from exc


def get_submission_for_employee_period(
    employee_id: int, period_id: int
) -> RdvSubmission | None:
    with session_scope() as session:
        return session.scalar(
            select(RdvSubmission)
            .options(
                selectinload(RdvSubmission.entries),
                joinedload(RdvSubmission.employee),
                joinedload(RdvSubmission.period),
            )
            .where(
                RdvSubmission.employee_id == employee_id,
                RdvSubmission.period_id == period_id,
            )
        )


def get_rdv(submission_id: int) -> RdvSubmission | None:
    with session_scope() as session:
        return session.scalar(
            select(RdvSubmission)
            .options(
                selectinload(RdvSubmission.entries),
                joinedload(RdvSubmission.employee),
                joinedload(RdvSubmission.period),
            )
            .where(RdvSubmission.id == submission_id)
        )


def get_rdvs(
    employee_id: int | None = None,
    role: EmployeeRole | str | None = None,
    period_id: int | None = None,
    status: SubmissionStatus | str | None = None,
    search: str = "",
    submitted_from: date | None = None,
    submitted_to: date | None = None,
) -> list[RdvSubmission]:
    with session_scope() as session:
        statement = select(RdvSubmission).options(
            selectinload(RdvSubmission.entries),
            joinedload(RdvSubmission.employee),
            joinedload(RdvSubmission.period),
        )
        if employee_id:
            statement = statement.where(RdvSubmission.employee_id == employee_id)
        if role or search.strip():
            statement = statement.join(RdvSubmission.employee)
        if role:
            statement = statement.where(Employee.role == _role(role))
        if period_id:
            statement = statement.where(RdvSubmission.period_id == period_id)
        if status:
            statement = statement.where(
                RdvSubmission.status
                == SubmissionStatus(str(getattr(status, "value", status)))
            )
        if search.strip():
            statement = statement.where(Employee.name.ilike(f"%{search.strip()}%"))
        if submitted_from:
            statement = statement.where(
                func.date(RdvSubmission.submitted_at) >= submitted_from
            )
        if submitted_to:
            statement = statement.where(
                func.date(RdvSubmission.submitted_at) <= submitted_to
            )
        return list(
            session.scalars(
                statement.order_by(RdvSubmission.submitted_at.desc())
            ).unique()
        )


def approve_rdv(submission_id: int) -> RdvSubmission:
    with session_scope() as session:
        submission = session.get(RdvSubmission, submission_id)
        if not submission:
            raise BusinessError("RDV não encontrado.")
        if submission.status != SubmissionStatus.ENVIADO:
            raise BusinessError("Somente um RDV enviado pode ser aprovado.")
        submission.status = SubmissionStatus.APROVADO
        submission.reviewed_at = now_sp()
        submission.admin_comment = None
        submission.updated_at = now_sp()
        session.flush()
        logger.info("RDV aprovado: id=%s", submission.id)
    return get_rdv(submission_id)  # type: ignore[return-value]


def reject_rdv(submission_id: int, reason: str) -> RdvSubmission:
    reason = clean_text(reason, "Motivo", 1000, required=True)
    with session_scope() as session:
        submission = session.get(RdvSubmission, submission_id)
        if not submission:
            raise BusinessError("RDV não encontrado.")
        if submission.status != SubmissionStatus.ENVIADO:
            raise BusinessError("Somente um RDV enviado pode ser rejeitado.")
        submission.status = SubmissionStatus.REJEITADO
        submission.reviewed_at = now_sp()
        submission.admin_comment = reason
        submission.updated_at = now_sp()
        session.flush()
        logger.info("RDV rejeitado: id=%s", submission.id)
    return get_rdv(submission_id)  # type: ignore[return-value]


def dashboard_stats(period_id: int | None = None) -> dict[str, Any]:
    rdvs = get_rdvs(period_id=period_id)
    counts = {status.value: 0 for status in SubmissionStatus}
    expense_total = Decimal("0.00")
    for rdv in rdvs:
        counts[rdv.status.value] += 1
        expense_total += calculate_rdv_totals(rdv.entries, rdv.advance_amount)[
            "expense_total"
        ]
    return {"counts": counts, "expense_total": expense_total, "total": len(rdvs)}
