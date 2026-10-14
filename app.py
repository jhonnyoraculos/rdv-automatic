from __future__ import annotations

import logging

import streamlit as st

from auth import (
    AdminRole,
    current_admin_role,
    is_authenticated,
    is_employee_authenticated,
    restore_employee_login,
)
from browser_session import load_employee_browser_token
from database import init_db
from services import ensure_default_employees, get_active_period
from ui import apply_style

st.set_page_config(
    page_title="RDV | JR Ferragens & Madeiras",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
init_db()
ensure_default_employees()
get_active_period()
apply_style()
restore_employee_login(load_employee_browser_token())

public_page = st.Page(
    "pages/formulario.py", title="Enviar RDV", icon="🧾", url_path="rdv"
)
login_page = st.Page(
    "pages/admin_login.py", title="Acessar", icon="🔐", url_path="acesso"
)

if is_authenticated():
    admin_pages = [
        st.Page(
            "pages/admin_dashboard.py",
            title="Painel RDV",
            icon="📊",
            url_path="painel",
        ),
        st.Page(
            "pages/admin_colaboradores.py",
            title="Colaboradores",
            icon="👥",
            url_path="colaboradores",
        ),
        st.Page(
            "pages/admin_periodos.py",
            title="Períodos",
            icon="📅",
            url_path="periodos",
        ),
    ]
    if current_admin_role() == AdminRole.ANALISTA:
        admin_pages.append(
            st.Page(
                "pages/admin_configuracoes.py",
                title="Valores das despesas",
                icon="⚙️",
                url_path="configuracoes",
            )
        )
    admin_pages.append(login_page)
    navigation = st.navigation({"Administração": admin_pages})
else:
    if is_employee_authenticated():
        navigation = st.navigation({"Colaborador": [public_page, login_page]})
    else:
        navigation = st.navigation([login_page])

navigation.run()
