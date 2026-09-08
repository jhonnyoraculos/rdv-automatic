from streamlit.testing.v1 import AppTest


def test_streamlit_pdf_viewer_loads_without_exception() -> None:
    script = """
from io import BytesIO
import streamlit as st
from reportlab.pdfgen.canvas import Canvas

buffer = BytesIO()
canvas = Canvas(buffer)
canvas.drawString(10, 10, "RDV")
canvas.save()
st.pdf(buffer.getvalue(), height=600)
"""
    app = AppTest.from_string(script, default_timeout=20).run()
    assert not app.exception
