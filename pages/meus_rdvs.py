from __future__ import annotations

import pandas as pd
import streamlit as st

from auth import current_employee_id, logout
from exports import PDF_LAYOUT_VERSION, pdf_to_png, rdv_to_pdf, rdv_to_xlsx
from print_document import print_pdf_button
from services import (
    BusinessError,
    get_employee,
    get_rdv,
    get_rdvs,
    reopen_rdv_for_editing,
)
from ui import company_header, require_employee, status_badge, submission_status_label
from utils import (
    calculate_rdv_totals,
    format_brl,
    format_date,
    format_datetime,
    protocol,
)

require_employee()
company_header(
    "Meus RDVs",
    "Histórico das folhas enviadas, impressão e acompanhamento",
)

employee_id = current_employee_id()
employee = get_employee(employee_id) if employee_id is not None else None
if not employee or not employee.active:
    logout()
    st.error("Seu acesso não está mais ativo. Procure o responsável pela frota.")
    st.stop()

rdvs = get_rdvs(employee_id=employee.id)
if not rdvs:
    st.info("Você ainda não enviou nenhum RDV.")
    st.stop()

rows = []
for item in rdvs:
    totals = calculate_rdv_totals(item.entries, item.advance_amount)
    rows.append(
        {
            "Protocolo": protocol(item.id),
            "Período": (
                f"{format_date(item.period.start_date)} a "
                f"{format_date(item.period.end_date)}"
            ),
            "Enviado em": format_datetime(item.submitted_at),
            "Total": format_brl(totals["expense_total"]),
            "Status": submission_status_label(item.status),
        }
    )

st.subheader("Histórico de envios")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

available_ids = [item.id for item in rdvs]
selected_id = st.session_state.get("employee_opened_rdv_id")
if selected_id not in available_ids:
    selected_id = available_ids[0]
selected_index = available_ids.index(selected_id)
selected_id = st.selectbox(
    "Abrir minha folha",
    available_ids,
    index=selected_index,
    format_func=lambda value: next(
        (
            f"{protocol(item.id)} — "
            f"{format_date(item.period.start_date)} a "
            f"{format_date(item.period.end_date)} — "
            f"{submission_status_label(item.status)}"
        )
        for item in rdvs
        if item.id == value
    ),
)
st.session_state["employee_opened_rdv_id"] = selected_id

rdv = get_rdv(selected_id)
if not rdv or rdv.employee_id != employee.id:
    st.error("RDV não encontrado.")
    st.stop()

st.divider()
st.subheader(f"{protocol(rdv.id)} — {rdv.employee.name}")
status_badge(rdv.status.value)
detail_cols = st.columns(3)
detail_cols[0].write(
    f"**Período:** {format_date(rdv.period.start_date)} a "
    f"{format_date(rdv.period.end_date)}"
)
detail_cols[1].write(f"**Enviado em:** {format_datetime(rdv.submitted_at)}")
detail_cols[2].write(f"**Status:** {submission_status_label(rdv.status)}")

st.info(
    "Esta é a sua folha enviada. Você pode imprimir mesmo enquanto ela aguarda "
    "a análise. O status CONCLUÍDO será exibido depois da aprovação."
)

edit_confirm_key = f"employee_confirm_reopen_{rdv.id}"
if st.button("EDITAR ESTE RDV", use_container_width=True):
    st.session_state[edit_confirm_key] = True
if st.session_state.get(edit_confirm_key):
    if rdv.status.value == "APROVADO":
        st.warning(
            "Esta folha já foi concluída. Ao editar, a aprovação será cancelada "
            "e o RDV precisará ser enviado novamente. Confirmar?"
        )
    else:
        st.warning(
            "O RDV voltará para edição e precisará ser enviado novamente. "
            "Confirmar?"
        )
    edit_col, cancel_col = st.columns(2)
    if edit_col.button(
        "SIM, EDITAR",
        type="primary",
        use_container_width=True,
        key=f"employee_reopen_{rdv.id}",
    ):
        try:
            reopen_rdv_for_editing(rdv.id, employee_id=employee.id)
            st.session_state["employee_period_selector"] = rdv.period_id
            st.session_state.pop(edit_confirm_key, None)
            st.session_state.pop("rdv_context", None)
            st.switch_page("pages/formulario.py")
        except BusinessError as exc:
            st.error(str(exc))
    if cancel_col.button(
        "NÃO",
        use_container_width=True,
        key=f"employee_cancel_reopen_{rdv.id}",
    ):
        st.session_state.pop(edit_confirm_key, None)
        st.rerun()

pdf_data = rdv_to_pdf(rdv)
png_data = pdf_to_png(pdf_data)
print_pdf_button(
    pdf_data,
    key=f"print_employee_rdv_{rdv.id}_{rdv.updated_at}_{PDF_LAYOUT_VERSION}",
)

mobile_tab, pdf_tab = st.tabs(["Visualização para celular", "Visualização em PDF"])
with mobile_tab:
    st.image(png_data, use_container_width=True)
with pdf_tab:
    st.pdf(
        pdf_data,
        height=800,
        key=f"employee_rdv_pdf_{rdv.id}_{rdv.updated_at}_{PDF_LAYOUT_VERSION}",
    )

download_cols = st.columns(3)
download_cols[0].download_button(
    "BAIXAR PDF",
    pdf_data,
    f"rdv_{rdv.id:06d}.pdf",
    "application/pdf",
    use_container_width=True,
)
download_cols[1].download_button(
    "BAIXAR PNG",
    png_data,
    f"rdv_{rdv.id:06d}.png",
    "image/png",
    use_container_width=True,
)
download_cols[2].download_button(
    "BAIXAR EXCEL",
    rdv_to_xlsx(rdv),
    f"rdv_{rdv.id:06d}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
