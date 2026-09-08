from __future__ import annotations

import csv
from collections.abc import Iterable
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from models import BenefitType, EmployeeRole, RdvSubmission
from utils import (
    calculate_rdv_totals,
    format_brl,
    format_date,
    protocol,
)


def _entry_rows(rdv: RdvSubmission) -> list[list[object]]:
    return [
        [
            protocol(rdv.id),
            rdv.employee.name,
            rdv.employee.role.value,
            format_date(entry.date),
            entry.city,
            entry.hotel_name,
            float(entry.hotel_amount),
            entry.benefit_type.value,
            float(entry.benefit_amount),
            rdv.status.value,
        ]
        for entry in rdv.entries
    ]


EXPORT_HEADERS = [
    "Protocolo",
    "Colaborador",
    "Função",
    "Data",
    "Cidade",
    "Hotel",
    "Valor hotel",
    "Tipo",
    "Valor benefício",
    "Status",
]


def rdv_to_csv(rdv: RdvSubmission) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(EXPORT_HEADERS)
    writer.writerows(_entry_rows(rdv))
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def rdvs_to_xlsx(rdvs: Iterable[RdvSubmission]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "RDVs"
    sheet.append(EXPORT_HEADERS)
    header_fill = PatternFill("solid", fgColor="B5122B")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for rdv in rdvs:
        for row in _entry_rows(rdv):
            sheet.append(row)
    for row in sheet.iter_rows(min_row=2):
        row[6].number_format = "R$ #,##0.00"
        row[8].number_format = "R$ #,##0.00"
    widths = [16, 34, 18, 14, 24, 28, 16, 16, 18, 14]
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def rdv_to_xlsx(rdv: RdvSubmission) -> bytes:
    return rdvs_to_xlsx([rdv])


def _draw_logo(canvas: object, x: float, y: float) -> None:
    from reportlab.lib.colors import HexColor, white

    canvas.setFillColor(HexColor("#C8102E"))
    canvas.roundRect(x, y, 22, 22, 4, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawCentredString(x + 11, y + 7, "JR")


def rdv_to_pdf(rdv: RdvSubmission) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen.canvas import Canvas

    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    canvas = Canvas(buffer, pagesize=(page_width, page_height))
    margin = 25
    top = page_height - 28
    _draw_logo(canvas, margin, top - 14)
    role_title = (
        "MOTORISTA"
        if rdv.employee.role == EmployeeRole.MOTORISTA
        else "AJUDANTE DE MOTORISTA"
    )
    title = f"RELATÓRIO DE DESPESAS DE VIAGEM - RDV - {role_title}"
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica-Bold", 17)
    canvas.drawCentredString(page_width / 2, top, title)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(margin, top - 16, f"NOME: {rdv.employee.name}")
    canvas.setFont("Helvetica", 8.5)
    period_text = f"DATA QUINZENA (INÍCIO E FINAL): {format_date(rdv.period.start_date)} a {format_date(rdv.period.end_date)}"
    canvas.drawRightString(page_width - margin, top - 16, period_text)
    canvas.drawString(
        margin,
        top - 32,
        f"HOUVE ADIANTAMENTO DE DIÁRIA?  {'(X) NÃO' if not rdv.advance_received else '( ) NÃO'}  "
        f"{'(X) SIM' if rdv.advance_received else '( ) SIM'}        NO VALOR DE {format_brl(rdv.advance_amount)}",
    )

    table_top = top - 40
    table_bottom = 182
    table_width = page_width - 2 * margin
    is_helper = rdv.employee.role == EmployeeRole.AJUDANTE
    fractions = [0.13, 0.24, 0.24, 0.15, 0.24] if is_helper else [0.16, 0.32, 0.52]
    headers = (
        ["DATA", "CIDADE", "HOTEL", "VALOR HOTEL", "DIÁRIA / TICKET"]
        if is_helper
        else ["DATA", "CIDADE", "DIÁRIA EM VIAGEM / TICKET ALIMENTAÇÃO"]
    )
    xs = [margin]
    for fraction in fractions:
        xs.append(xs[-1] + table_width * fraction)
    rows = max(len(rdv.entries) + 1, 2)
    row_height = (table_top - table_bottom) / rows
    canvas.setLineWidth(0.6)
    for x in xs:
        canvas.line(x, table_bottom, x, table_top)
    for row in range(rows + 1):
        y = table_top - row * row_height
        canvas.line(margin, y, page_width - margin, y)
    canvas.setFont("Helvetica-Bold", 8.5)
    for index, header in enumerate(headers):
        canvas.drawString(xs[index] + 3, table_top - row_height + 6, header)
    canvas.setFont("Helvetica", 8)
    for row_index, entry in enumerate(rdv.entries, 1):
        y = table_top - (row_index + 1) * row_height + 6
        date_label = "DOMINGO" if entry.date.weekday() == 6 else format_date(entry.date)
        values: list[str]
        benefit = ""
        if entry.benefit_type != BenefitType.NONE:
            label = "DIÁRIA" if entry.benefit_type == BenefitType.DIARIA else "TICKET"
            benefit = f"{label}: {format_brl(entry.benefit_amount)}"
        if is_helper:
            values = [
                date_label,
                entry.city,
                entry.hotel_name,
                format_brl(entry.hotel_amount) if entry.hotel_amount else "",
                benefit,
            ]
        else:
            values = [date_label, entry.city, benefit]
        for col_index, value in enumerate(values):
            max_width = xs[col_index + 1] - xs[col_index] - 6
            text = str(value)
            while text and stringWidth(text, "Helvetica", 8) > max_width:
                text = text[:-1]
            if text != str(value):
                text = text[:-3] + "..."
            canvas.drawString(xs[col_index] + 3, y, text)

    totals = calculate_rdv_totals(rdv.entries, rdv.advance_amount)
    y = table_bottom - 19
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(
        margin,
        y,
        f"TOTAL DA QUINZENA EM R$ -----> {format_brl(totals['expense_total'])}",
    )
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(
        margin,
        y - 23,
        "LOCAL/DATA: ____________________________________________, ____ de ____________ de ____________",
    )
    signature_y = y - 68
    labels = ["ASSINATURA DO COLABORADOR", "ANALISTA DE FROTA", "GESTOR DE FROTA"]
    signature_width = (table_width - 30) / 3
    for index, label in enumerate(labels):
        start = margin + index * (signature_width + 15)
        canvas.drawCentredString(start + signature_width / 2, signature_y + 23, label)
        canvas.line(start, signature_y, start + signature_width, signature_y)
    observation = (
        "OBSERVAÇÃO: NOS TERMOS DA CONVENÇÃO COLETIVA, A DIÁRIA DE VIAGEM É DESTINADA AO COLABORADOR QUE EXERCE "
        "ATIVIDADE FORA DA BASE. CONSIDERA-SE CADA PERÍODO MODULAR DE 24 HORAS. O RECEBIMENTO DA DIÁRIA EXCLUI O "
        "PAGAMENTO DA AJUDA DE ALIMENTAÇÃO (TICKET)."
    )
    canvas.setFont("Helvetica", 6.5)
    text = canvas.beginText(margin, 35)
    max_chars = 190
    remaining = observation
    while remaining:
        split = min(max_chars, len(remaining))
        if split < len(remaining):
            split = remaining.rfind(" ", 0, split)
        text.textLine(remaining[:split])
        remaining = remaining[split:].lstrip()
    canvas.drawText(text)
    canvas.setTitle(protocol(rdv.id))
    canvas.save()
    return buffer.getvalue()
