from __future__ import annotations

from typing import NamedTuple

import streamlit as st

from exports import (
    PDF_LAYOUT_VERSION,
    pdf_to_png,
    rdv_to_csv,
    rdv_to_pdf,
    rdv_to_xlsx,
    rdvs_to_xlsx,
)
from models import RdvSubmission
from services import get_rdv


class RdvArtifacts(NamedTuple):
    pdf: bytes
    png: bytes
    xlsx: bytes
    csv: bytes


@st.cache_data(show_spinner=False, max_entries=128)
def cached_rdv_artifacts(
    submission_id: int,
    revision: str,
    layout_version: str = PDF_LAYOUT_VERSION,
    _rdv: RdvSubmission | None = None,
) -> RdvArtifacts:
    """Render immutable artifacts once per RDV revision and document layout."""
    del revision, layout_version
    rdv = _rdv or get_rdv(submission_id)
    if not rdv:
        raise ValueError("RDV não encontrado para gerar os documentos.")
    pdf = rdv_to_pdf(rdv)
    return RdvArtifacts(
        pdf=pdf,
        png=pdf_to_png(pdf),
        xlsx=rdv_to_xlsx(rdv),
        csv=rdv_to_csv(rdv),
    )


@st.cache_data(show_spinner=False, max_entries=64)
def cached_rdvs_xlsx(
    revisions: tuple[tuple[int, str], ...],
    _rdvs: tuple[RdvSubmission, ...] = (),
) -> bytes:
    """Build a filtered workbook only when one of its RDVs has changed."""
    rdvs = list(_rdvs)
    if not rdvs:
        for submission_id, _revision in revisions:
            rdv = get_rdv(submission_id)
            if rdv:
                rdvs.append(rdv)
    return rdvs_to_xlsx(rdvs)
