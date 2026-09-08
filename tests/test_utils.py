from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from utils import (
    calculate_rdv_totals,
    date_range,
    format_brl,
    format_long_date,
    money,
    signature_from_canvas,
    validate_signature_png,
)


def test_brazilian_money_format() -> None:
    assert format_brl(Decimal("1250.5")) == "R$ 1.250,50"


def test_brazilian_money_format_accepts_calculated_negative_balance() -> None:
    assert format_brl(Decimal("-130.25")) == "R$ -130,25"


def test_money_rejects_negative() -> None:
    with pytest.raises(ValueError):
        money("-0.01")


def test_date_range_is_inclusive() -> None:
    assert date_range(date(2026, 9, 2), date(2026, 9, 4)) == [
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]


def test_long_date_in_portuguese() -> None:
    assert format_long_date(date(2026, 9, 8)) == "08 de setembro de 2026"


def test_canvas_requires_real_strokes_and_creates_valid_png() -> None:
    blank = np.full((80, 240, 4), 255, dtype=np.uint8)
    assert signature_from_canvas(blank) is None
    blank[20:25, 20:220, :3] = 0
    signature = signature_from_canvas(blank)
    assert signature is not None
    assert validate_signature_png(signature).startswith(b"\x89PNG")


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
        "expense_total": Decimal("120.35"),
        "advance_total": Decimal("30.00"),
        "balance": Decimal("120.35"),
    }


def test_hotel_and_advance_do_not_change_fortnight_total() -> None:
    entries = [
        {
            "benefit_type": "DIARIA",
            "benefit_amount": "80.00",
            "hotel_amount": "900.00",
        }
    ]
    totals = calculate_rdv_totals(entries, "500.00")
    assert totals["expense_total"] == Decimal("80.00")
    assert totals["hotel_total"] == Decimal("900.00")
    assert totals["advance_total"] == Decimal("500.00")
