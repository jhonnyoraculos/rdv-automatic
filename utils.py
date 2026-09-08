from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
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
MONTHS_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
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


def format_long_date(value: date | None) -> str:
    if not value:
        return ""
    return f"{value.day:02d} de {MONTHS_PT[value.month - 1]} de {value.year}"


def signature_from_canvas(image_data: Any) -> bytes | None:
    """Crop real ink from the drawing canvas and return a transparent PNG."""
    if image_data is None:
        return None

    import numpy as np
    from PIL import Image

    pixels = np.asarray(image_data)
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        return None
    pixels = np.clip(pixels, 0, 255).astype(np.uint8)
    rgb = pixels[:, :, :3]
    alpha = pixels[:, :, 3] if pixels.shape[2] == 4 else np.full(rgb.shape[:2], 255)
    grayscale = rgb.mean(axis=2)
    ink = (grayscale < 235) & (alpha > 10)
    if int(ink.sum()) < 40:
        return None

    ys, xs = np.where(ink)
    padding = 8
    x1 = max(int(xs.min()) - padding, 0)
    x2 = min(int(xs.max()) + padding + 1, pixels.shape[1])
    y1 = max(int(ys.min()) - padding, 0)
    y2 = min(int(ys.max()) + padding + 1, pixels.shape[0])
    cropped_gray = grayscale[y1:y2, x1:x2]
    cropped_alpha = alpha[y1:y2, x1:x2]
    output_alpha = np.minimum(255 - cropped_gray, cropped_alpha).astype(np.uint8)
    output = np.zeros((*output_alpha.shape, 4), dtype=np.uint8)
    output[:, :, 3] = output_alpha
    stream = BytesIO()
    Image.fromarray(output, "RGBA").save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def validate_signature_png(value: Any) -> bytes:
    if not isinstance(value, bytes) or not 100 <= len(value) <= 1_000_000:
        raise ValueError("Faça sua assinatura no campo indicado.")

    import numpy as np
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(BytesIO(value)) as image:
            if image.format != "PNG":
                raise ValueError("A assinatura deve estar no formato PNG.")
            if image.width > 2000 or image.height > 1000:
                raise ValueError("A imagem da assinatura é muito grande.")
            pixels = np.asarray(image.convert("RGBA"))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise ValueError("A assinatura desenhada é inválida.") from exc
    if signature_from_canvas(pixels) is None:
        raise ValueError("Faça sua assinatura no campo indicado.")
    return value


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
