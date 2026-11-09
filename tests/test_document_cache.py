from __future__ import annotations

import document_cache


def test_rdv_artifacts_are_reused_until_revision_changes(monkeypatch) -> None:
    calls = {"load": 0, "pdf": 0, "png": 0, "xlsx": 0, "csv": 0}
    rdv = object()

    def load_rdv(_submission_id: int):
        calls["load"] += 1
        return rdv

    def artifact(name: str, value: bytes):
        def build(_source):
            calls[name] += 1
            return value

        return build

    monkeypatch.setattr(document_cache, "get_rdv", load_rdv)
    monkeypatch.setattr(document_cache, "rdv_to_pdf", artifact("pdf", b"pdf"))
    monkeypatch.setattr(document_cache, "pdf_to_png", artifact("png", b"png"))
    monkeypatch.setattr(document_cache, "rdv_to_xlsx", artifact("xlsx", b"xlsx"))
    monkeypatch.setattr(document_cache, "rdv_to_csv", artifact("csv", b"csv"))
    document_cache.cached_rdv_artifacts.clear()

    first = document_cache.cached_rdv_artifacts(7, "revision-1", _rdv=rdv)
    repeated = document_cache.cached_rdv_artifacts(7, "revision-1", _rdv=rdv)
    changed = document_cache.cached_rdv_artifacts(7, "revision-2", _rdv=rdv)

    assert first == repeated
    assert changed == first
    assert calls == {"load": 0, "pdf": 2, "png": 2, "xlsx": 2, "csv": 2}
    document_cache.cached_rdv_artifacts.clear()
