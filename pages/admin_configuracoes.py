from __future__ import annotations

import streamlit as st

from auth import AdminRole, current_admin_role, current_admin_username
from services import BusinessError, get_expense_settings, update_expense_settings
from ui import company_header, require_admin
from utils import format_brl, format_datetime

require_admin()
if current_admin_role() != AdminRole.ANALISTA:
    st.error("Somente o analista de frota pode alterar os valores das despesas.")
    st.stop()
company_header(
    "Valores das despesas",
    "Configuração dos valores fixos usados nos RDVs",
)

settings = get_expense_settings()
st.info(
    f"Valores atuais: Diária {format_brl(settings.daily_amount)} • "
    f"Ticket {format_brl(settings.ticket_amount)}"
)

with st.form("expense_settings"):
    value_columns = st.columns(2)
    daily_amount = value_columns[0].number_input(
        "Valor fixo da diária (R$)",
        min_value=0.01,
        value=float(settings.daily_amount),
        step=0.01,
        format="%.2f",
    )
    ticket_amount = value_columns[1].number_input(
        "Valor fixo do ticket (R$)",
        min_value=0.01,
        value=float(settings.ticket_amount),
        step=0.01,
        format="%.2f",
    )
    save = st.form_submit_button(
        "SALVAR VALORES FIXOS", type="primary", use_container_width=True
    )

if save:
    try:
        update_expense_settings(
            daily_amount,
            ticket_amount,
            current_admin_username(),
        )
        st.success("Valores atualizados. Os colaboradores não podem alterá-los.")
        st.rerun()
    except BusinessError as exc:
        st.error(str(exc))

st.caption(
    "Os novos valores são aplicados aos rascunhos e aos próximos envios. "
    "RDVs que já foram enviados ou aprovados preservam os valores registrados."
)
st.caption(
    f"Última alteração: {format_datetime(settings.updated_at)} • "
    f"Responsável: {settings.updated_by or '—'}"
)
