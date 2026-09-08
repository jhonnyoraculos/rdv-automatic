from streamlit.testing.v1 import AppTest


def test_responsive_signature_canvas_loads_without_exception() -> None:
    script = """
from signature_component import signature_pad

result = signature_pad(key="signature_test")
assert result is None
"""
    app = AppTest.from_string(script, default_timeout=20).run()
    assert not app.exception
