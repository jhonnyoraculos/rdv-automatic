from __future__ import annotations

import streamlit as st

from auth import (
    AdminRole,
    auth_configured,
    current_admin_role,
    is_authenticated,
    login,
    logout,
)
from ui import company_header

company_header("Área administrativa", "Acesso restrito à gestão de frota")

if is_authenticated():
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

if not auth_configured():
    st.error("O acesso administrativo ainda não foi configurado.")
    st.code(
        "python -c \"import bcrypt; print(bcrypt.hashpw(b'SUA_SENHA', bcrypt.gensalt()).decode())\""
    )
    st.caption(
        "Configure ANALYST_PASSWORD_HASH e MANAGER_PASSWORD_HASH nos segredos do aplicativo."
    )
    st.stop()

with st.form("admin_login_form"):
    username = st.text_input("Usuário", max_chars=100)
    password = st.text_input("Senha", type="password", max_chars=200)
    submitted = st.form_submit_button(
        "ENTRAR", type="primary", use_container_width=True
    )
if submitted:
    if login(username, password):
        st.success("Acesso autorizado. Perfil identificado automaticamente.")
        st.rerun()
    else:
        st.error("Usuário ou senha inválidos.")
