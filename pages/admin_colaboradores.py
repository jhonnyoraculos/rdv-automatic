from __future__ import annotations

import pandas as pd
import streamlit as st

from auth import AdminRole, current_admin_role
from models import EmployeeRole
from services import (
    BusinessError,
    create_employee_with_access,
    get_employees,
    set_employee_password,
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
        fixed_password = st.text_input(
            "Senha fixa",
            max_chars=100,
            help="Mínimo de 8 caracteres. Esta senha permanecerá válida até você alterá-la.",
        )
        password_confirmation = st.text_input(
            "Confirme a senha fixa",
            max_chars=100,
        )
        submit = st.form_submit_button("Cadastrar colaborador", type="primary")
    if submit:
        try:
            if fixed_password.strip() != password_confirmation.strip():
                raise BusinessError("A confirmação da senha não confere.")
            access = create_employee_with_access(
                name,
                role,
                active,
                password=fixed_password,
            )
            st.success("Colaborador cadastrado com sucesso.")
            st.code(
                f"Usuário: {access.username}\nSenha fixa: {access.temporary_password}",
                language=None,
            )
            st.caption(
                "A senha permanecerá válida até ser alterada manualmente nesta tela."
            )
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
                "Usuário": employee.username or "Acesso pendente",
                "Acesso": "Senha definida" if employee.password_hash else "Sem senha",
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
        if current_admin_role() == AdminRole.ANALISTA:
            st.write("**Preenchimento do RDV**")
            if st.button(
                "PREENCHER RDV PARA ESTE COLABORADOR",
                type="primary",
                use_container_width=True,
                disabled=not selected.active,
                key=f"fill_rdv_{selected.id}",
            ):
                st.session_state["admin_fill_employee_id"] = selected.id
                st.session_state["admin_fill_employee_selector"] = selected.id
                st.switch_page("pages/formulario.py")
            if not selected.active:
                st.caption("Ative o colaborador para preencher um RDV em nome dele.")
            st.divider()
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
            f"Usuário: {selected.username or 'será criado ao definir a senha'}"
        )
        st.caption(
            "A senha definida permanecerá válida. Preencha os campos abaixo somente quando quiser defini-la ou alterá-la."
        )
        with st.form(f"fixed_password_{selected.id}"):
            fixed_password = st.text_input(
                "Senha fixa",
                max_chars=100,
                help="Mínimo de 8 caracteres.",
            )
            password_confirmation = st.text_input(
                "Confirme a senha fixa",
                max_chars=100,
            )
            save_password = st.form_submit_button(
                "SALVAR SENHA FIXA",
                type="primary",
                use_container_width=True,
            )
        if save_password:
            try:
                if fixed_password.strip() != password_confirmation.strip():
                    raise BusinessError("A confirmação da senha não confere.")
                access = set_employee_password(selected.id, fixed_password)
                st.success(
                    "Senha fixa salva. Ela permanecerá válida até você alterá-la novamente."
                )
                st.code(
                    f"Usuário: {access.username}\nSenha fixa: {access.temporary_password}",
                    language=None,
                )
            except BusinessError as exc:
                st.error(str(exc))
st.caption(
    "Colaboradores com relatórios não são excluídos; desative o cadastro para preservar o histórico."
)
