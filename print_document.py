from __future__ import annotations

import base64

import streamlit as st

PRINT_PDF_HTML = (
    '<button class="rdv-print-button" type="button">'
    "ABRIR PDF PARA IMPRIMIR"
    "</button>"
)
PRINT_PDF_CSS = """
.rdv-print-button {
    width: 100%;
    min-height: 48px;
    padding: 0.7rem 1rem;
    border: 1px solid #b5122b;
    border-radius: 0.5rem;
    background: #b5122b;
    color: white;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
}
.rdv-print-button:hover { background: #941023; border-color: #941023; }
"""
PRINT_PDF_JS = """
export default function({ parentElement, data }) {
    const button = parentElement.querySelector('.rdv-print-button');
    button.onclick = () => {
        const binary = window.atob(data.pdfBase64);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            bytes[index] = binary.charCodeAt(index);
        }
        const blob = new Blob([bytes], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank', 'noopener,noreferrer');
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    };
}
"""

_print_pdf_control = st.components.v2.component(
    "rdv_print_pdf",
    html=PRINT_PDF_HTML,
    css=PRINT_PDF_CSS,
    js=PRINT_PDF_JS,
)


def print_pdf_button(pdf_data: bytes, *, key: str) -> None:
    _print_pdf_control(
        data={"pdfBase64": base64.b64encode(pdf_data).decode("ascii")},
        key=key,
    )
