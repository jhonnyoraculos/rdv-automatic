from datetime import date
from decimal import Decimal

import pytest

from utils import calculate_rdv_totals, date_range, format_brl, money


def test_brazilian_money_format() -> None:
    assert format_brl(Decimal("1250.5")) == "R$ 1.250,50"


def test_money_rejects_negative() -> None:
    with pytest.raises(ValueError):
        money("-0.01")


def test_date_range_is_inclusive() -> None:
    assert date_range(date(2026, 9, 2), date(2026, 9, 4)) == [
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]


def test_central_totals() -> None:
    entries = [
        {"benefit_type": "DIARIA", "benefit_amount": "100.10", "hotel_amount": "50"},
        {"benefit_type": "TICKET", "benefit_amount": "20.25", "hotel_amount": "0"},
        {"benefit_type": "NONE", "benefit_amount": "0", "hotel_amount": "0"},
    ]
    totals = calculate_rdv_totals(entries, "30")
    assert totals == {
        "daily_total": Decimal("100.10"),
        "ticket_total": Decimal("20.25"),
        "hotel_total": Decimal("50.00"),
        "expense_total": Decimal("170.35"),
        "advance_total": Decimal("30.00"),
        "balance": Decimal("140.35"),
    }
