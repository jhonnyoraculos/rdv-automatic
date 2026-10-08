from __future__ import annotations

import pandas as pd
import streamlit as st

from models import EmployeeRole
from services import (
    BusinessError,
    create_employee_with_access,
    generate_pending_employee_access,
    get_employees,
    reset_employee_password,
    update_employee,
)
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
            access = create_employee_with_access(name, role, active)
            st.success("Colaborador cadastrado com sucesso.")
            st.warning(
                "Copie os dados abaixo agora. A senha não será mostrada novamente."
            )
            st.code(
                f"Usuário: {access.username}\nSenha temporária: {access.temporary_password}",
                language=None,
            )
        except BusinessError as exc:
            st.error(str(exc))

with edit_tab:
    if st.button(
        "Gerar acessos pendentes",
        help="Cria uma senha temporária para todos os colaboradores que ainda não possuem acesso.",
    ):
        accesses = generate_pending_employee_access()
        if accesses:
            st.warning(
                "Copie estes acessos agora. As senhas não serão mostradas novamente."
            )
            st.code(
                "\n".join(
                    f"{item.employee.name} | Usuário: {item.username} | Senha: {item.temporary_password}"
                    for item in accesses
                ),
                language=None,
            )
        else:
            st.info("Todos os colaboradores ativos já possuem acesso.")
    search = st.text_input("Pesquisar por nome", key="employee_search")
    employees = get_employees(search=search)
    table = pd.DataFrame(
        [
            {
                "ID": employee.id,
                "Nome": employee.name,
                "Usuário": employee.username or "Acesso pendente",
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
        st.divider()
        st.write("**Acesso do colaborador**")
        st.caption(
            f"Usuário: {selected.username or 'será criado ao gerar a senha'}"
        )
        if st.button(
            "Gerar nova senha",
            type="primary",
            key=f"reset_password_{selected.id}",
        ):
            try:
                access = reset_employee_password(selected.id)
                st.warning(
                    "Copie os dados abaixo agora. A nova senha não será mostrada novamente."
                )
                st.code(
                    f"Usuário: {access.username}\nSenha temporária: {access.temporary_password}",
                    language=None,
                )
            except BusinessError as exc:
                st.error(str(exc))
st.caption(
    "Colaboradores com relatórios não são excluídos; desative o cadastro para preservar o histórico."
)
