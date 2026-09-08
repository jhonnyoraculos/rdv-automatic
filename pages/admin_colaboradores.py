from __future__ import annotations

import pandas as pd
import streamlit as st

from models import EmployeeRole
from services import BusinessError, create_employee, get_employees, update_employee
from ui import company_header, require_admin

require_admin()
company_header("Colaboradores", "Cadastro de motoristas e ajudantes")

create_tab, edit_tab = st.tabs(["Adicionar", "Editar / ativar / desativar"])
with create_tab:
    with st.form("create_employee"):
        name = st.text_input("Nome completo", max_chars=150)
        role = st.selectbox(
            "Função", list(EmployeeRole), format_func=lambda value: value.value
        )
        active = st.checkbox("Ativo", value=True)
        submit = st.form_submit_button("Cadastrar colaborador", type="primary")
    if submit:
        try:
            create_employee(name, role, active)
            st.success("Colaborador cadastrado com sucesso.")
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))

with edit_tab:
    search = st.text_input("Pesquisar por nome", key="employee_search")
    employees = get_employees(search=search)
    table = pd.DataFrame(
        [
            {
                "ID": employee.id,
                "Nome": employee.name,
                "Função": employee.role.value,
                "Status": "Ativo" if employee.active else "Inativo",
            }
            for employee in employees
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)
    selected_id = st.selectbox(
        "Selecione para editar",
        [None, *[employee.id for employee in employees]],
        format_func=lambda value: (
            "Selecione..."
            if value is None
            else next(employee.name for employee in employees if employee.id == value)
        ),
    )
    if selected_id is not None:
        selected = next(
            employee for employee in employees if employee.id == selected_id
        )
        with st.form(f"edit_employee_{selected.id}"):
            edited_name = st.text_input(
                "Nome completo", value=selected.name, max_chars=150
            )
            edited_role = st.selectbox(
                "Função",
                list(EmployeeRole),
                index=list(EmployeeRole).index(selected.role),
                format_func=lambda value: value.value,
            )
            edited_active = st.checkbox("Ativo", value=selected.active)
            save = st.form_submit_button("Salvar alterações", type="primary")
        if save:
            try:
                update_employee(selected.id, edited_name, edited_role, edited_active)
                st.success("Colaborador atualizado.")
                st.rerun()
            except BusinessError as exc:
                st.error(str(exc))
st.caption(
    "Colaboradores com relatórios não são excluídos; desative o cadastro para preservar o histórico."
)
