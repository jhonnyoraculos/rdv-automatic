from __future__ import annotations

import pandas as pd
import streamlit as st

from exports import rdv_to_csv, rdv_to_pdf, rdv_to_xlsx, rdvs_to_xlsx
from models import EmployeeRole, SubmissionStatus
from services import (
    BusinessError,
    approve_rdv,
    dashboard_stats,
    get_periods,
    get_rdv,
    get_rdvs,
    reject_rdv,
)
from ui import company_header, require_admin, status_badge
from utils import (
    calculate_rdv_totals,
    format_brl,
    format_date,
    format_datetime,
    now_sp,
    protocol,
)

require_admin()
company_header("Painel RDV", "Acompanhamento e análise dos relatórios enviados")

periods = get_periods()
period_by_id = {period.id: period for period in periods}
period_filter = st.selectbox(
    "Período para os indicadores",
    [None, *period_by_id],
    format_func=lambda value: (
        "Todos os períodos"
        if value is None
        else (
            f"{format_date(period_by_id[value].start_date)} a {format_date(period_by_id[value].end_date)}"
            f"{' • ATIVO' if period_by_id[value].active else ''}"
        )
    ),
    key="dashboard_period",
)
stats = dashboard_stats(period_filter)
metric_cols = st.columns(4)
metric_cols[0].metric("Aguardando análise", stats["counts"]["ENVIADO"])
metric_cols[1].metric("Aprovados", stats["counts"]["APROVADO"])
metric_cols[2].metric("Rejeitados", stats["counts"]["REJEITADO"])
metric_cols[3].metric("Total da quinzena", format_brl(stats["expense_total"]))
pending = stats["counts"]["ENVIADO"]
st.info(f"{pending} RDV{'s' if pending != 1 else ''} aguardando análise.")

st.subheader("Relatórios")
with st.expander("Filtros", expanded=False):
    filter_cols = st.columns(3)
    search = filter_cols[0].text_input("Pesquisar colaborador")
    role_filter = filter_cols[1].selectbox(
        "Função",
        [None, *EmployeeRole],
        format_func=lambda x: "Todas" if x is None else x.value,
    )
    status_filter = filter_cols[2].selectbox(
        "Status",
        [None, *SubmissionStatus],
        format_func=lambda x: "Todos" if x is None else x.value,
    )
    use_dates = st.checkbox("Filtrar pela data de envio")
    submitted_from = submitted_to = None
    if use_dates:
        today = now_sp().date()
        date_cols = st.columns(2)
        submitted_from = date_cols[0].date_input(
            "Enviado a partir de", value=today.replace(day=1)
        )
        submitted_to = date_cols[1].date_input("Enviado até", value=today)

rdvs = get_rdvs(
    period_id=period_filter,
    role=role_filter,
    status=status_filter,
    search=search,
    submitted_from=submitted_from,
    submitted_to=submitted_to,
)
rows = []
for rdv in rdvs:
    total = calculate_rdv_totals(rdv.entries, rdv.advance_amount)["expense_total"]
    rows.append(
        {
            "Protocolo": protocol(rdv.id),
            "Colaborador": rdv.employee.name,
            "Função": rdv.employee.role.value,
            "Período": f"{format_date(rdv.period.start_date)} a {format_date(rdv.period.end_date)}",
            "Total": format_brl(total),
            "Envio": format_datetime(rdv.submitted_at),
            "Status": rdv.status.value,
        }
    )
rdv_table = pd.DataFrame(rows)
if not rdv_table.empty:
    status_colors = {
        "ENVIADO": "background-color: #fff1cc; color: #8a5b00; font-weight: 700",
        "APROVADO": "background-color: #dff6e8; color: #116b39; font-weight: 700",
        "REJEITADO": "background-color: #fde2e5; color: #a11427; font-weight: 700",
    }
    rdv_table = rdv_table.style.map(
        lambda value: status_colors.get(str(value), ""), subset=["Status"]
    )
st.dataframe(rdv_table, use_container_width=True, hide_index=True)
if rdvs:
    st.download_button(
        "Baixar Excel dos resultados filtrados",
        data=rdvs_to_xlsx(rdvs),
        file_name="rdvs_filtrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.caption("Nenhum RDV encontrado com os filtros escolhidos.")

selected_id = st.selectbox(
    "Abrir relatório",
    [None, *[rdv.id for rdv in rdvs]],
    format_func=lambda value: (
        "Selecione um protocolo..."
        if value is None
        else next(
            f"{protocol(item.id)} — {item.employee.name}"
            for item in rdvs
            if item.id == value
        )
    ),
    key="selected_rdv_id",
)
if selected_id is None:
    st.stop()

rdv = get_rdv(selected_id)
if not rdv:
    st.error("RDV não encontrado.")
    st.stop()

st.divider()
st.subheader(f"{protocol(rdv.id)} — {rdv.employee.name}")
status_badge(rdv.status.value)
details_left, details_right = st.columns(2)
with details_left:
    st.write(f"**Função:** {rdv.employee.role.value}")
    st.write(
        f"**Período:** {format_date(rdv.period.start_date)} a {format_date(rdv.period.end_date)}"
    )
    st.write(f"**Data do envio:** {format_datetime(rdv.submitted_at)}")
with details_right:
    st.write(
        f"**Adiantamento:** {'Sim' if rdv.advance_received else 'Não'} — {format_brl(rdv.advance_amount)}"
    )
    st.write(f"**Revisado em:** {format_datetime(rdv.reviewed_at)}")
    if rdv.admin_comment:
        st.write(f"**Motivo da rejeição:** {rdv.admin_comment}")

entry_rows = [
    {
        "Data": format_date(entry.date),
        "Cidade": entry.city or "—",
        "Hotel": entry.hotel_name or "—",
        "Valor hotel": format_brl(entry.hotel_amount),
        "Tipo": {"NONE": "Nenhum", "DIARIA": "Diária", "TICKET": "Ticket"}[
            entry.benefit_type.value
        ],
        "Valor": format_brl(entry.benefit_amount),
    }
    for entry in rdv.entries
]
st.dataframe(pd.DataFrame(entry_rows), use_container_width=True, hide_index=True)
totals = calculate_rdv_totals(rdv.entries, rdv.advance_amount)
total_cols = st.columns(3)
total_cols[0].metric("Total diária", format_brl(totals["daily_total"]))
total_cols[1].metric("Total ticket", format_brl(totals["ticket_total"]))
total_cols[2].metric("Total hotel (informativo)", format_brl(totals["hotel_total"]))
total_cols = st.columns(2)
total_cols[0].metric("Total da quinzena", format_brl(totals["expense_total"]))
total_cols[1].metric("Adiantamento (informativo)", format_brl(totals["advance_total"]))
st.caption("O total da quinzena considera somente diárias e tickets.")

download_cols = st.columns(3)
download_cols[0].download_button(
    "Baixar PDF",
    rdv_to_pdf(rdv),
    f"rdv_{rdv.id:06d}.pdf",
    "application/pdf",
    use_container_width=True,
)
download_cols[1].download_button(
    "Baixar Excel",
    rdv_to_xlsx(rdv),
    f"rdv_{rdv.id:06d}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
download_cols[2].download_button(
    "Baixar CSV",
    rdv_to_csv(rdv),
    f"rdv_{rdv.id:06d}.csv",
    "text/csv",
    use_container_width=True,
)

if rdv.status == SubmissionStatus.ENVIADO:
    st.subheader("Análise")
    action_cols = st.columns(2)
    if action_cols[0].button("APROVAR RDV", type="primary", use_container_width=True):
        try:
            approve_rdv(rdv.id)
            st.success("RDV aprovado.")
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))
    with action_cols[1]:
        with st.form(f"reject_{rdv.id}"):
            reason = st.text_area("Motivo obrigatório para rejeitar", max_chars=1000)
            reject = st.form_submit_button("REJEITAR RDV", use_container_width=True)
        if reject:
            try:
                reject_rdv(rdv.id, reason)
                st.success("RDV rejeitado e liberado para correção.")
                st.rerun()
            except BusinessError as exc:
                st.error(str(exc))
