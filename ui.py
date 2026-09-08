from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st

from auth import is_authenticated

APP_CSS = """
<style>
    :root { --jr-red: #b5122b; --jr-blue: #143a66; --ink: #172033; }
    .stApp { background: #f5f7fa; color: var(--ink); }
    .block-container { max-width: 1180px; padding-top: 1.6rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.02em; }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e5e9f0; border-radius: 14px;
        padding: 1rem 1.1rem; box-shadow: 0 5px 20px rgba(20,58,102,.05);
    }
    div[data-testid="stMetric"] label { color: #596274; }
    div[data-testid="stExpander"] { background: white; border: 1px solid #e2e7ee; border-radius: 12px; }
    div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] {
        background: var(--jr-red); border-color: var(--jr-red); font-weight: 700;
    }
    .jr-header {
        display:flex; align-items:center; gap:14px; background:white; padding:16px 20px;
        border-radius:16px; border-top:4px solid var(--jr-red); margin-bottom:1rem;
        box-shadow:0 7px 26px rgba(20,58,102,.07);
    }
    .jr-logo {
        width:48px; height:48px; border-radius:10px; object-fit:contain; flex:0 0 48px;
    }
    .jr-header h1 { margin:0; font-size:1.5rem; }
    .jr-header p { margin:3px 0 0; color:#667085; }
    .info-strip { background:#eef3f9; border-left:4px solid var(--jr-blue); padding:12px 15px; border-radius:8px; }
    .status { display:inline-block; padding:4px 9px; border-radius:99px; font-size:.78rem; font-weight:800; }
    .status-enviado { background:#fff1cc; color:#8a5b00; }
    .status-aguardando_gestor { background:#dcecff; color:#154f8b; }
    .status-aprovado { background:#dff6e8; color:#116b39; }
    .status-rejeitado { background:#fde2e5; color:#a11427; }
    @media (max-width: 640px) {
        .block-container { padding: .8rem .75rem 2rem; }
        .jr-header { padding:12px; }
        .jr-header h1 { font-size:1.18rem; }
        div[data-testid="stHorizontalBlock"] { flex-wrap:wrap; }
        div[data-testid="column"] { min-width:100% !important; width:100% !important; }
        div.stButton > button, div.stDownloadButton > button { min-height:48px; }
        div[data-testid="stDataFrame"] { overflow-x:auto; }
        iframe, img { max-width:100%; }
    }
</style>
"""


def apply_style() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def company_header(title: str, subtitle: str = "JR Ferragens & Madeiras") -> None:
    logo_path = Path(__file__).resolve().parent / "assets" / "logo_jr.png"
    logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    st.markdown(
        f'<div class="jr-header"><img class="jr-logo" src="data:image/png;base64,{logo_data}" '
        f'alt="Logo JR"><div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div></div>',
        unsafe_allow_html=True,
    )


def require_admin() -> None:
    if not is_authenticated():
        st.error("Acesso restrito. Entre com uma conta administrativa.")
        if st.button("Ir para o login", type="primary"):
            st.switch_page("pages/admin_login.py")
        st.stop()


def status_badge(status: str) -> None:
    normalized = status.lower()
    st.markdown(
        f'<span class="status status-{normalized}">{submission_status_label(status)}</span>',
        unsafe_allow_html=True,
    )


def submission_status_label(status: object) -> str:
    value = str(getattr(status, "value", status))
    return {
        "ENVIADO": "AGUARDANDO ANALISTA",
        "AGUARDANDO_GESTOR": "AGUARDANDO GESTOR",
        "APROVADO": "CONCLUÍDO",
        "REJEITADO": "REJEITADO",
    }.get(value, value)
