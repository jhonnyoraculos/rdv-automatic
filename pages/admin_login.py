from __future__ import annotations

import streamlit as st

from auth import (
    AdminRole,
    auth_configured,
    current_admin_role,
    is_authenticated,
    is_employee_authenticated,
    login,
    login_employee,
    logout,
)
from ui import company_header

company_header("Acesso ao RDV", "Entre com seu usuário e senha")

if is_authenticated():
    if st.session_state.pop("post_login_redirect", None) == "admin":
        st.switch_page("pages/admin_dashboard.py")
    role = current_admin_role()
    role_label = (
        "Analista de frota" if role == AdminRole.ANALISTA else "Gestor de frota"
    )
    st.success(
        f"Sessão ativa como {st.session_state.get('admin_username', 'administrador')} — {role_label}."
    )
    enter_col, logout_col = st.columns(2)
    if enter_col.button("Abrir Painel RDV", type="primary", use_container_width=True):
        st.switch_page("pages/admin_dashboard.py")
    if logout_col.button("Sair", use_container_width=True):
        logout()
        st.rerun()
    st.stop()

if is_employee_authenticated():
    if st.session_state.pop("post_login_redirect", None) == "employee":
        st.switch_page("pages/formulario.py")
    st.success(
        f"Sessão ativa como {st.session_state.get('employee_name', 'colaborador')}."
    )
    enter_col, logout_col = st.columns(2)
    if enter_col.button("Abrir Enviar RDV", type="primary", use_container_width=True):
        st.switch_page("pages/formulario.py")
    if logout_col.button("Sair", use_container_width=True):
        logout()
        st.rerun()
    st.stop()

with st.form("login_form"):
    username = st.text_input("Usuário", max_chars=100)
    password = st.text_input("Senha", type="password", max_chars=200)
    submitted = st.form_submit_button(
        "ENTRAR", type="primary", use_container_width=True
    )
if submitted:
    if login(username, password):
        st.session_state["post_login_redirect"] = "admin"
        st.rerun()
    elif login_employee(username, password):
        st.session_state["post_login_redirect"] = "employee"
        st.rerun()
    else:
        st.error("Usuário ou senha inválidos.")

if not auth_configured():
    st.caption("O acesso administrativo ainda não foi configurado.")
