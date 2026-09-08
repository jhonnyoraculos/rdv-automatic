from __future__ import annotations

import logging

import streamlit as st

from auth import is_authenticated
from database import init_db
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
apply_style()

public_page = st.Page(
    "pages/formulario.py", title="Enviar RDV", icon="🧾", default=True, url_path="rdv"
)
login_page = st.Page(
    "pages/admin_login.py", title="Área administrativa", icon="🔐", url_path="admin"
)

if is_authenticated():
    navigation = st.navigation(
        {
            "Colaborador": [public_page],
            "Administração": [
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
                login_page,
            ],
        }
    )
else:
    navigation = st.navigation({"Acesso": [public_page, login_page]})

navigation.run()
