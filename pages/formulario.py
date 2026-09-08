from __future__ import annotations

import logging
from html import escape

import pandas as pd
import streamlit as st

from models import BenefitType, EmployeeRole, SubmissionStatus
from services import (
    BusinessError,
    create_rdv,
    get_active_employees,
    get_active_period,
    get_submission_for_employee_period,
)
from ui import company_header
from utils import (
    WEEKDAYS_PT,
    calculate_rdv_totals,
    date_range,
    format_brl,
    format_date,
    money,
    protocol,
)

company_header(
    "Relatório de Despesas de Viagem — RDV",
    "Preenchimento digital para motoristas e ajudantes",
)

logger = logging.getLogger("rdv.ui")

period = get_active_period()
employees = get_active_employees()
if not period:
    st.info(
        "Não há um período de RDV ativo no momento. Procure o responsável pela frota."
    )
    st.stop()
if not employees:
    st.info(
        "Não há colaboradores ativos cadastrados. Procure o responsável pela frota."
    )
    st.stop()

employee_by_id = {employee.id: employee for employee in employees}
employee_id = st.selectbox(
    "Selecione seu nome",
    options=[None, *employee_by_id],
    format_func=lambda value: (
        "Pesquisar colaborador..." if value is None else employee_by_id[value].name
    ),
    key="public_employee_id",
)
if employee_id is None:
    st.caption("Digite parte do nome no campo acima para pesquisar.")
    st.stop()

employee = employee_by_id[employee_id]
base_context = f"{employee.id}_{period.id}"
existing = get_submission_for_employee_period(employee.id, period.id)
if st.session_state.get("rdv_success_context") == base_context and st.session_state.get(
    "rdv_success"
):
    st.success(f"RDV enviado com sucesso! Protocolo: {st.session_state['rdv_success']}")
    st.balloons()
    st.stop()
if existing and existing.status in (
    SubmissionStatus.ENVIADO,
    SubmissionStatus.APROVADO,
):
    st.success(
        f"Já existe um RDV enviado para este colaborador neste período: {protocol(existing.id)}."
    )
    st.caption(
        f"Status atual: {existing.status.value}. Em caso de dúvida, fale com o responsável pela frota."
    )
    st.stop()

revision = (
    existing.updated_at.strftime("%Y%m%d%H%M%S%f")
    if existing and existing.status == SubmissionStatus.REJEITADO
    else "novo"
)
context = f"{base_context}_{revision}"
if st.session_state.get("rdv_context") != context:
    st.session_state["rdv_context"] = context
    st.session_state["rdv_confirm"] = False
    st.session_state.pop("rdv_success", None)
    st.session_state.pop("rdv_success_context", None)
    saved_entries = (
        {entry.date: entry for entry in existing.entries} if existing else {}
    )
    st.session_state[f"advance_{context}"] = (
        "Sim" if existing and existing.advance_received else "Não"
    )
    st.session_state[f"advance_value_{context}"] = (
        float(existing.advance_amount) if existing else 0.0
    )
    for day in date_range(period.start_date, period.end_date):
        saved = saved_entries.get(day)
        suffix = f"{context}_{day:%Y_%m_%d}"
        st.session_state[f"city_{suffix}"] = saved.city if saved else ""
        st.session_state[f"hotel_{suffix}"] = saved.hotel_name if saved else ""
        st.session_state[f"hotel_value_{suffix}"] = (
            float(saved.hotel_amount) if saved else 0.0
        )
        st.session_state[f"benefit_{suffix}"] = (
            saved.benefit_type.value if saved else BenefitType.NONE.value
        )
        st.session_state[f"benefit_value_{suffix}"] = (
            float(saved.benefit_amount) if saved else 0.0
        )

if existing and existing.status == SubmissionStatus.REJEITADO:
    st.warning(
        f"Este RDV foi devolvido para correção. Motivo: {existing.admin_comment}"
    )

role_label = (
    "Motorista" if employee.role == EmployeeRole.MOTORISTA else "Ajudante de motorista"
)
st.markdown(
    f'<div class="info-strip"><b>Nome:</b> {escape(employee.name)}<br><b>Função:</b> {role_label}<br>'
    f"<b>Período:</b> {format_date(period.start_date)} até {format_date(period.end_date)}</div>",
    unsafe_allow_html=True,
)

st.subheader("Adiantamento")
advance_answer = st.radio(
    "Houve adiantamento de diária?",
    ["Não", "Sim"],
    horizontal=True,
    key=f"advance_{context}",
)
if advance_answer == "Sim":
    advance_value = st.number_input(
        "Valor do adiantamento (R$)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        key=f"advance_value_{context}",
    )
else:
    advance_value = 0.0

st.subheader("Lançamentos do período")
st.caption("Abra cada data para informar cidade e despesas. Domingos estão destacados.")
entries: list[dict[str, object]] = []
benefit_options = [item.value for item in BenefitType]
benefit_labels = {"NONE": "Nenhum", "DIARIA": "Diária", "TICKET": "Ticket"}
for day in date_range(period.start_date, period.end_date):
    suffix = f"{context}_{day:%Y_%m_%d}"
    sunday = day.weekday() == 6
    expander_title = (
        f"{format_date(day)} — {'DOMINGO' if sunday else WEEKDAYS_PT[day.weekday()]}"
    )
    with st.expander(expander_title, expanded=False):
        city = st.text_input("Cidade", max_chars=120, key=f"city_{suffix}")
        hotel_name = ""
        hotel_amount = 0.0
        if employee.role == EmployeeRole.AJUDANTE:
            hotel_col, hotel_value_col = st.columns([2, 1])
            with hotel_col:
                hotel_name = st.text_input(
                    "Hotel", max_chars=150, key=f"hotel_{suffix}"
                )
            with hotel_value_col:
                hotel_amount = st.number_input(
                    "Valor do hotel (R$)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=f"hotel_value_{suffix}",
                )
        type_col, value_col = st.columns([2, 1])
        with type_col:
            benefit_type = st.selectbox(
                "Tipo da despesa",
                benefit_options,
                format_func=lambda value: benefit_labels[value],
                key=f"benefit_{suffix}",
            )
        with value_col:
            if benefit_type != BenefitType.NONE.value:
                benefit_amount = st.number_input(
                    "Valor (R$)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=f"benefit_value_{suffix}",
                )
            else:
                benefit_amount = 0.0
        entries.append(
            {
                "date": day,
                "city": city,
                "hotel_name": hotel_name,
                "hotel_amount": money(hotel_amount),
                "benefit_type": benefit_type,
                "benefit_amount": money(benefit_amount),
            }
        )

totals = calculate_rdv_totals(entries, advance_value)
st.subheader("Resumo do RDV")
metric_columns = st.columns(4)
metric_columns[0].metric("Diárias", format_brl(totals["daily_total"]))
metric_columns[1].metric("Tickets", format_brl(totals["ticket_total"]))
metric_columns[2].metric("Hotéis", format_brl(totals["hotel_total"]))
metric_columns[3].metric("Total de despesas", format_brl(totals["expense_total"]))
if advance_answer == "Sim":
    advance_columns = st.columns(2)
    advance_columns[0].metric(
        "Adiantamento recebido", format_brl(totals["advance_total"])
    )
    advance_columns[1].metric("Saldo", format_brl(totals["balance"]))

st.subheader("Revisão")
review_rows = []
for entry in entries:
    review_rows.append(
        {
            "Data": format_date(entry["date"]),
            "Cidade": entry["city"] or "—",
            "Hotel": entry["hotel_name"] or "—",
            "Valor hotel": format_brl(entry["hotel_amount"]),
            "Tipo": benefit_labels[str(entry["benefit_type"])],
            "Valor": format_brl(entry["benefit_amount"]),
        }
    )
review_df = pd.DataFrame(review_rows)
if employee.role == EmployeeRole.MOTORISTA:
    review_df = review_df.drop(columns=["Hotel", "Valor hotel"])
st.dataframe(review_df, use_container_width=True, hide_index=True)

confirmed = st.checkbox(
    "Confirmo que revisei as informações e que os valores informados estão corretos.",
    key=f"reviewed_{context}",
)
if st.button(
    "CONFIRMAR E ENVIAR RDV",
    type="primary",
    disabled=not confirmed,
    use_container_width=True,
):
    st.session_state["rdv_confirm"] = True

if st.session_state.get("rdv_confirm"):
    st.warning(
        "Confirma o envio definitivo deste RDV? Depois do envio, alterações dependerão da devolução pelo administrador."
    )
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button(
        "Sim, enviar agora", type="primary", use_container_width=True
    ):
        try:
            saved = create_rdv(
                employee.id,
                period.id,
                advance_answer == "Sim",
                advance_value,
                entries,
            )
            st.session_state["rdv_success"] = protocol(saved.id)
            st.session_state["rdv_success_context"] = base_context
            st.session_state["rdv_confirm"] = False
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))
        except Exception:
            logger.exception("Falha inesperada ao enviar RDV")
            st.error(
                "Não foi possível enviar o RDV. Tente novamente ou procure o responsável pela frota."
            )
    if cancel_col.button("Voltar e revisar", use_container_width=True):
        st.session_state["rdv_confirm"] = False
        st.rerun()
