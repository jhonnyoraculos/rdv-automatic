from streamlit.testing.v1 import AppTest


def test_signature_canvas_loads_without_exception() -> None:
    script = """
from streamlit_drawable_canvas import st_canvas

result = st_canvas(
    stroke_width=3,
    stroke_color="#172033",
    background_color="#FFFFFF",
    height=180,
    width=700,
    drawing_mode="freedraw",
    return_image_data=True,
    key="signature_test",
)
assert result is not None
"""
    app = AppTest.from_string(script, default_timeout=20).run()
    assert not app.exception
