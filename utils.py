from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
MONEY_QUANT = Decimal("0.01")
WEEKDAYS_PT = (
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
)


def now_sp() -> datetime:
    return datetime.now(SAO_PAULO)


def money(value: Any, field: str = "Valor") -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        result = Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} inválido.") from exc
    if result < 0:
        raise ValueError(f"{field} não pode ser negativo.")
    return result


def format_brl(value: Any) -> str:
    # Formatting must support legitimate calculated negatives (for example,
    # when the advance is greater than the expenses). Input validation remains
    # strict in money().
    try:
        amount = Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Valor inválido para formatação.") from exc
    formatted = f"{amount:,.2f}"
    return "R$ " + formatted.translate(str.maketrans({",": ".", ".": ","}))


def format_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def format_datetime(value: datetime | None) -> str:
    if not value:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=SAO_PAULO)
    return value.astimezone(SAO_PAULO).strftime("%d/%m/%Y %H:%M")


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("A data final deve ser igual ou posterior à inicial.")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def clean_text(value: Any, field: str, max_length: int, required: bool = False) -> str:
    result = " ".join(str(value or "").strip().split())
    if required and not result:
        raise ValueError(f"{field} é obrigatório.")
    if len(result) > max_length:
        raise ValueError(f"{field} deve ter no máximo {max_length} caracteres.")
    return result


def protocol(submission_id: int) -> str:
    return f"RDV #{submission_id:06d}"


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def calculate_rdv_totals(
    entries: Iterable[Any], advance_amount: Any = 0
) -> dict[str, Decimal]:
    daily_total = Decimal("0.00")
    ticket_total = Decimal("0.00")
    hotel_total = Decimal("0.00")
    for entry in entries:
        kind = enum_value(
            entry.get("benefit_type") if isinstance(entry, dict) else entry.benefit_type
        )
        benefit = money(
            entry.get("benefit_amount", 0)
            if isinstance(entry, dict)
            else entry.benefit_amount
        )
        hotel = money(
            entry.get("hotel_amount", 0)
            if isinstance(entry, dict)
            else entry.hotel_amount
        )
        if kind == "DIARIA":
            daily_total += benefit
        elif kind == "TICKET":
            ticket_total += benefit
        hotel_total += hotel
    # Regra da empresa: hotel e adiantamento são apenas informativos.
    # O total da quinzena considera exclusivamente diária e ticket.
    expense_total = daily_total + ticket_total
    advance_total = money(advance_amount, "Adiantamento")
    return {
        "daily_total": daily_total.quantize(MONEY_QUANT),
        "ticket_total": ticket_total.quantize(MONEY_QUANT),
        "hotel_total": hotel_total.quantize(MONEY_QUANT),
        "expense_total": expense_total.quantize(MONEY_QUANT),
        "advance_total": advance_total,
        "balance": expense_total.quantize(MONEY_QUANT),
    }
