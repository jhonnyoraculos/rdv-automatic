from __future__ import annotations

import pandas as pd
import streamlit as st

from services import BusinessError, create_period, get_periods, update_period
from ui import company_header, require_admin
from utils import format_date, now_sp

require_admin()
company_header(
    "Períodos RDV", "Criação e controle das quinzenas de prestação de contas"
)

create_tab, edit_tab = st.tabs(["Criar período", "Editar / ativar / encerrar"])
with create_tab:
    with st.form("create_period"):
        today = now_sp().date()
        date_cols = st.columns(2)
        start_date = date_cols[0].date_input("Data inicial", value=today)
        end_date = date_cols[1].date_input("Data final", value=today)
        description = st.text_input(
            "Descrição (opcional)",
            max_chars=150,
            placeholder="Ex.: 1ª quinzena de setembro",
        )
        active = st.checkbox("Tornar este o período ativo", value=True)
        submit = st.form_submit_button("Criar período", type="primary")
    if submit:
        try:
            create_period(start_date, end_date, description, active)
            st.success("Período criado com sucesso.")
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))

with edit_tab:
    periods = get_periods()
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": period.id,
                    "Início": format_date(period.start_date),
                    "Fim": format_date(period.end_date),
                    "Descrição": period.description or "—",
                    "Status": "ATIVO" if period.active else "Encerrado",
                }
                for period in periods
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    selected_id = st.selectbox(
        "Selecione um período",
        [None, *[period.id for period in periods]],
        format_func=lambda value: (
            "Selecione..."
            if value is None
            else next(
                f"{format_date(period.start_date)} a {format_date(period.end_date)}"
                for period in periods
                if period.id == value
            )
        ),
    )
    if selected_id is not None:
        selected = next(period for period in periods if period.id == selected_id)
        with st.form(f"edit_period_{selected.id}"):
            date_cols = st.columns(2)
            edited_start = date_cols[0].date_input(
                "Data inicial", value=selected.start_date
            )
            edited_end = date_cols[1].date_input("Data final", value=selected.end_date)
            edited_description = st.text_input(
                "Descrição", value=selected.description, max_chars=150
            )
            edited_active = st.checkbox("Período ativo", value=selected.active)
            save = st.form_submit_button("Salvar alterações", type="primary")
        if save:
            try:
                update_period(
                    selected.id,
                    edited_start,
                    edited_end,
                    edited_description,
                    edited_active,
                )
                st.success("Período atualizado.")
                st.rerun()
            except BusinessError as exc:
                st.error(str(exc))
st.info(
    "Ao ativar um período, qualquer outro período ativo é encerrado automaticamente."
)
