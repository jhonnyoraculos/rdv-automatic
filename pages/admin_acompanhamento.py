from __future__ import annotations

import pandas as pd
import streamlit as st

from models import BenefitType, EmployeeRole, SubmissionStatus
from services import BusinessError, get_live_rdv_progress, get_periods
from ui import company_header, require_admin, submission_status_label
from utils import (
    calculate_rdv_totals,
    format_brl,
    format_date,
    format_datetime,
    now_sp,
)

require_admin()
company_header(
    "Acompanhamento ao vivo",
    "Veja o preenchimento dos colaboradores antes mesmo do envio",
)

periods = get_periods()
if not periods:
    st.info("Não há nenhum período cadastrado para acompanhar.")
    st.stop()

period_by_id = {period.id: period for period in periods}
period_ids = list(period_by_id)
active_period_id = next((period.id for period in periods if period.active), None)
default_period_id = active_period_id or period_ids[0]
selected_period_id = st.selectbox(
    "Período acompanhado",
    period_ids,
    index=period_ids.index(default_period_id),
    format_func=lambda value: (
        f"{format_date(period_by_id[value].start_date)} a "
        f"{format_date(period_by_id[value].end_date)}"
        f"{' • ATIVO' if period_by_id[value].active else ''}"
    ),
    key="live_progress_period",
)

st.caption(
    "A tela consulta os rascunhos automaticamente a cada 5 segundos. "
    "As alterações aparecem depois que o colaborador sai do campo preenchido."
)


def _live_status(status: SubmissionStatus | None) -> str:
    if status is None:
        return "NÃO INICIOU"
    if status == SubmissionStatus.RASCUNHO:
        return "PREENCHENDO"
    if status == SubmissionStatus.REJEITADO:
        return "EM CORREÇÃO"
    return submission_status_label(status)


@st.fragment(run_every="5s", key=f"live_progress_{selected_period_id}")
def render_live_progress() -> None:
    try:
        progress = get_live_rdv_progress(selected_period_id)
    except BusinessError as exc:
        st.error(str(exc))
        return

    not_started = sum(item.submission is None for item in progress)
    filling = sum(
        bool(
            item.submission
            and item.submission.status
            in {SubmissionStatus.RASCUNHO, SubmissionStatus.REJEITADO}
        )
        for item in progress
    )
    sent = len(progress) - not_started - filling
    metric_cols = st.columns(4)
    metric_cols[0].metric("Colaboradores ativos", len(progress))
    metric_cols[1].metric("Preenchendo", filling)
    metric_cols[2].metric("Não iniciaram", not_started)
    metric_cols[3].metric("Enviados/concluídos", sent)

    search = st.text_input(
        "Pesquisar colaborador",
        key=f"live_progress_search_{selected_period_id}",
    ).strip()
    visible_progress = [
        item
        for item in progress
        if not search or search.casefold() in item.employee.name.casefold()
    ]
    rows = []
    for item in visible_progress:
        submission = item.submission
        total = (
            calculate_rdv_totals(submission.entries, submission.advance_amount)[
                "expense_total"
            ]
            if submission
            else 0
        )
        completion = (
            round(item.filled_days * 100 / item.total_days)
            if item.total_days
            else 0
        )
        rows.append(
            {
                "Colaborador": item.employee.name,
                "Função": item.employee.role.value,
                "Situação": _live_status(
                    submission.status if submission else None
                ),
                "Dias com dados": f"{item.filled_days}/{item.total_days}",
                "Progresso": completion,
                "Total": format_brl(total),
                "Local": submission.location or "—" if submission else "—",
                "Último salvamento": (
                    format_datetime(submission.updated_at) if submission else "—"
                ),
            }
        )
    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Progresso": st.column_config.ProgressColumn(
                    "Progresso", min_value=0, max_value=100, format="%d%%"
                )
            },
        )
    else:
        st.info("Nenhum colaborador encontrado.")

    st.caption(f"Última atualização: {format_datetime(now_sp())}")
    visible_employee_ids = [item.employee.id for item in visible_progress]
    detail_key = f"live_progress_employee_{selected_period_id}"
    if st.session_state.get(detail_key) not in [None, *visible_employee_ids]:
        st.session_state[detail_key] = None
    selected_employee_id = st.selectbox(
        "Ver preenchimento detalhado",
        [None, *visible_employee_ids],
        format_func=lambda value: (
            "Selecione um colaborador..."
            if value is None
            else next(
                item.employee.name
                for item in visible_progress
                if item.employee.id == value
            )
        ),
        key=detail_key,
    )
    if selected_employee_id is None:
        return

    selected = next(
        item for item in progress if item.employee.id == selected_employee_id
    )
    submission = selected.submission
    st.subheader(selected.employee.name)
    if not submission:
        st.info("Este colaborador ainda não iniciou o preenchimento deste período.")
        return

    details = st.columns(4)
    details[0].metric("Situação", _live_status(submission.status))
    details[1].metric(
        "Dias com dados", f"{selected.filled_days}/{selected.total_days}"
    )
    details[2].metric("Local", submission.location or "—")
    details[3].metric("Salvo em", format_datetime(submission.updated_at)[-5:])

    entry_rows = []
    for entry in submission.entries:
        row = {
            "Data": format_date(entry.date),
            "Cidade": entry.city or "—",
            "Tipo": {
                BenefitType.NONE: "Nenhum",
                BenefitType.DIARIA: "Diária",
                BenefitType.TICKET: "Ticket",
            }[entry.benefit_type],
            "Valor": format_brl(entry.benefit_amount),
        }
        if selected.employee.role == EmployeeRole.AJUDANTE:
            row["Hotel"] = entry.hotel_name or "—"
            row["Valor hotel"] = format_brl(entry.hotel_amount)
        entry_rows.append(row)
    st.dataframe(
        pd.DataFrame(entry_rows),
        use_container_width=True,
        hide_index=True,
    )


render_live_progress()
