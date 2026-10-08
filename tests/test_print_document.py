import base64

import print_document


def test_print_button_opens_the_generated_pdf(monkeypatch) -> None:
    mounted = {}
    monkeypatch.setattr(
        print_document,
        "_print_pdf_control",
        lambda **kwargs: mounted.update(kwargs),
    )

    print_document.print_pdf_button(b"%PDF-test", key="print-test")

    encoded = mounted["data"]["pdfBase64"]
    assert base64.b64decode(encoded) == b"%PDF-test"
    assert mounted["key"] == "print-test"
    assert "window.open" in print_document.PRINT_PDF_JS
