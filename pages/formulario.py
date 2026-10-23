from __future__ import annotations

import logging
from html import escape
from types import SimpleNamespace

import streamlit as st

from auth import (
    AdminRole,
    current_admin_role,
    current_employee_id,
    is_authenticated,
    logout,
)
from exports import PDF_LAYOUT_VERSION, pdf_to_png, rdv_to_pdf
from models import BenefitType, EmployeeRole, SubmissionStatus
from print_document import print_pdf_button
from services import (
    BusinessError,
    create_rdv,
    get_active_employees,
    get_active_period,
    get_employee,
    get_expense_settings,
    get_periods,
    get_submission_for_employee_period,
    save_rdv_draft,
)
from ui import company_header, require_admin, require_employee
from utils import (
    WEEKDAYS_PT,
    calculate_rdv_totals,
    date_range,
    format_brl,
    format_date,
    format_datetime,
    money,
    protocol,
)

admin_fill_mode = is_authenticated()
if admin_fill_mode:
    require_admin()
    if current_admin_role() != AdminRole.ANALISTA:
        st.error("Somente o analista pode preencher um RDV para um colaborador.")
        st.stop()
else:
    require_employee()

company_header(
    "Relatório de Despesas de Viagem — RDV",
    (
        "Preenchimento administrativo em nome do colaborador"
        if admin_fill_mode
        else "Preenchimento digital para motoristas e ajudantes"
    ),
)

logger = logging.getLogger("rdv.ui")

if admin_fill_mode:
    active_employees = get_active_employees()
    employee_ids = [item.id for item in active_employees]
    requested_employee_id = st.session_state.get("admin_fill_employee_id")
    if requested_employee_id not in employee_ids:
        requested_employee_id = None
    selector_key = "admin_fill_employee_selector"
    if st.session_state.get(selector_key) not in employee_ids:
        st.session_state[selector_key] = requested_employee_id
    employee_id = st.selectbox(
        "Escolha o colaborador",
        [None, *employee_ids],
        format_func=lambda value: (
            "Selecione..."
            if value is None
            else next(
                item.name for item in active_employees if item.id == value
            )
        ),
        key=selector_key,
    )
    st.session_state["admin_fill_employee_id"] = employee_id
    if employee_id is None:
        st.info("Selecione um colaborador para preencher o RDV em nome dele.")
        st.stop()

    periods = get_periods()
    if not periods:
        st.info("Não há nenhum período de RDV cadastrado.")
        st.stop()
    period_by_id = {item.id: item for item in periods}
    period_ids = list(period_by_id)
    active_period_id = next((item.id for item in periods if item.active), None)
    period_selector_key = "admin_fill_period_selector"
    if st.session_state.get(period_selector_key) not in period_ids:
        st.session_state[period_selector_key] = (
            active_period_id or (period_ids[0] if period_ids else None)
        )
    period_id = st.selectbox(
        "Escolha o período",
        period_ids,
        format_func=lambda value: (
            f"{format_date(period_by_id[value].start_date)} a "
            f"{format_date(period_by_id[value].end_date)}"
            f"{' • ATIVO' if period_by_id[value].active else ''}"
        ),
        key=period_selector_key,
    )
    period = period_by_id.get(period_id)
    if st.button("VOLTAR AOS COLABORADORES"):
        st.switch_page("pages/admin_colaboradores.py")
else:
    employee_id = current_employee_id()
    principal_period = get_active_period()
    period = principal_period
    if principal_period:
        available_periods = [
            item
            for item in get_periods()
            if item.start_date <= principal_period.start_date
        ]
        period_by_id = {item.id: item for item in available_periods}
        period_ids = list(period_by_id)
        period_selector_key = "employee_period_selector"
        if st.session_state.get(period_selector_key) not in period_ids:
            st.session_state[period_selector_key] = principal_period.id
        period_id = st.selectbox(
            "Escolha o período",
            period_ids,
            format_func=lambda value: (
                f"{format_date(period_by_id[value].start_date)} a "
                f"{format_date(period_by_id[value].end_date)}"
                f"{' • PRINCIPAL' if value == principal_period.id else ''}"
            ),
            key=period_selector_key,
            help=(
                "O período principal muda somente na segunda-feira em que a "
                "nova quinzena começa."
            ),
        )
        period = period_by_id.get(period_id)

employee = get_employee(employee_id) if employee_id is not None else None
if not employee or not employee.active:
    if admin_fill_mode:
        st.error("O colaborador selecionado não está ativo.")
    else:
        logout()
        st.error("Seu acesso não está mais ativo. Procure o responsável pela frota.")
    st.stop()
if not period:
    if admin_fill_mode:
        st.info("Não há nenhum período de RDV cadastrado.")
    else:
        st.info(
            "Não há um período de RDV ativo no momento. "
            "Procure o responsável pela frota."
        )
    st.stop()
expense_settings = get_expense_settings()

base_context = f"{employee.id}_{period.id}"
existing = get_submission_for_employee_period(employee.id, period.id)
if (
    st.session_state.get("rdv_success_context") == base_context
    and st.session_state.get("rdv_success")
    and existing
    and existing.status != SubmissionStatus.APROVADO
):
    st.success(f"RDV enviado com sucesso! Protocolo: {st.session_state['rdv_success']}")
    st.balloons()
    if admin_fill_mode and st.button("IR PARA O PAINEL RDV", type="primary"):
        st.switch_page("pages/admin_dashboard.py")
    if not admin_fill_mode and st.button(
        "ABRIR E IMPRIMIR MINHA FOLHA", type="primary"
    ):
        st.session_state["employee_opened_rdv_id"] = existing.id
        st.switch_page("pages/meus_rdvs.py")
    st.stop()
if existing and existing.status == SubmissionStatus.APROVADO:
    st.success(
        f"RDV concluído! Protocolo: {protocol(existing.id)}. Todas as aprovações foram realizadas."
    )
    final_pdf = rdv_to_pdf(existing)
    final_png = pdf_to_png(final_pdf)
    st.subheader("Folha final do RDV")
    print_pdf_button(
        final_pdf,
        key=f"print_employee_approved_{existing.id}_{existing.updated_at}",
    )
    mobile_tab, pdf_tab = st.tabs(["Visualização para celular", "Visualização em PDF"])
    with mobile_tab:
        st.image(final_png, use_container_width=True)
    with pdf_tab:
        st.pdf(
            final_pdf,
            height=800,
            key=f"public_final_pdf_{existing.id}_{PDF_LAYOUT_VERSION}",
        )
    pdf_col, png_col = st.columns(2)
    pdf_col.download_button(
        "BAIXAR EM PDF",
        final_pdf,
        f"rdv_concluido_{existing.id:06d}.pdf",
        "application/pdf",
        type="primary",
        use_container_width=True,
    )
    png_col.download_button(
        "BAIXAR EM PNG",
        final_png,
        f"rdv_concluido_{existing.id:06d}.png",
        "image/png",
        use_container_width=True,
    )
    st.stop()
if existing and existing.status in (
    SubmissionStatus.ENVIADO,
    SubmissionStatus.AGUARDANDO_GESTOR,
):
    st.success(
        f"Já existe um RDV enviado para este colaborador neste período: {protocol(existing.id)}."
    )
    status_label = {
        SubmissionStatus.ENVIADO: "Aguardando análise",
        SubmissionStatus.AGUARDANDO_GESTOR: "Aguardando aprovação do analista",
    }[existing.status]
    st.caption(
        f"Status atual: {status_label}. Em caso de dúvida, fale com o responsável pela frota."
    )
    if not admin_fill_mode and st.button(
        "ABRIR E IMPRIMIR MINHA FOLHA", type="primary"
    ):
        st.session_state["employee_opened_rdv_id"] = existing.id
        st.switch_page("pages/meus_rdvs.py")
    st.stop()

revision = (
    existing.updated_at.strftime("%Y%m%d%H%M%S%f")
    if existing and existing.status == SubmissionStatus.REJEITADO
    else "novo"
)
context = f"{base_context}_{revision}"
if st.session_state.get("rdv_context") != context:
    st.session_state["rdv_context"] = context
    st.session_state["rdv_confirm"] = False
    st.session_state.pop("rdv_success", None)
    st.session_state.pop("rdv_success_context", None)
    saved_entries = (
        {entry.date: entry for entry in existing.entries} if existing else {}
    )
    st.session_state[f"advance_{context}"] = (
        "Sim" if existing and existing.advance_received else "Não"
    )
    st.session_state[f"advance_value_{context}"] = (
        float(existing.advance_amount) if existing else 0.0
    )
    st.session_state[f"location_{context}"] = existing.location if existing else ""
    for day in date_range(period.start_date, period.end_date):
        saved = saved_entries.get(day)
        suffix = f"{context}_{day:%Y_%m_%d}"
        st.session_state[f"city_{suffix}"] = saved.city if saved else ""
        st.session_state[f"hotel_{suffix}"] = saved.hotel_name if saved else ""
        st.session_state[f"hotel_value_{suffix}"] = (
            float(saved.hotel_amount) if saved else 0.0
        )
        st.session_state[f"benefit_{suffix}"] = (
            saved.benefit_type.value if saved else BenefitType.NONE.value
        )

if (
    existing
    and existing.admin_comment
    and existing.status in {SubmissionStatus.RASCUNHO, SubmissionStatus.REJEITADO}
):
    st.warning(
        f"Este RDV foi devolvido para correção. Motivo: {existing.admin_comment}"
    )

role_label = (
    "Motorista" if employee.role == EmployeeRole.MOTORISTA else "Ajudante de motorista"
)
st.markdown(
    f'<div class="info-strip"><b>Nome:</b> {escape(employee.name)}<br><b>Função:</b> {role_label}<br>'
    f"<b>Período:</b> {format_date(period.start_date)} até {format_date(period.end_date)}</div>",
    unsafe_allow_html=True,
)

st.subheader("Adiantamento")
advance_answer = st.radio(
    "Houve adiantamento de diária?",
    ["Não", "Sim"],
    horizontal=True,
    key=f"advance_{context}",
)
if advance_answer == "Sim":
    advance_value = st.number_input(
        "Valor do adiantamento (R$)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        key=f"advance_value_{context}",
    )
else:
    advance_value = 0.0

st.subheader("Lançamentos do período")
st.caption("Abra cada data para informar cidade e despesas. Domingos estão destacados.")
entries: list[dict[str, object]] = []
benefit_options = [item.value for item in BenefitType]
benefit_option_labels = {
    "NONE": "Nenhum",
    "DIARIA": f"Diária — {format_brl(expense_settings.daily_amount)}",
    "TICKET": f"Ticket — {format_brl(expense_settings.ticket_amount)}",
}
fixed_benefit_values = {
    BenefitType.DIARIA.value: expense_settings.daily_amount,
    BenefitType.TICKET.value: expense_settings.ticket_amount,
}
for day in date_range(period.start_date, period.end_date):
    suffix = f"{context}_{day:%Y_%m_%d}"
    sunday = day.weekday() == 6
    expander_title = (
        f"{format_date(day)} — {'DOMINGO' if sunday else WEEKDAYS_PT[day.weekday()]}"
    )
    with st.expander(expander_title, expanded=False):
        city = st.text_input("Cidade", max_chars=120, key=f"city_{suffix}")
        hotel_name = ""
        hotel_amount = 0.0
        if employee.role == EmployeeRole.AJUDANTE:
            hotel_col, hotel_value_col = st.columns([2, 1])
            with hotel_col:
                hotel_name = st.text_input(
                    "Hotel", max_chars=150, key=f"hotel_{suffix}"
                )
            with hotel_value_col:
                hotel_amount = st.number_input(
                    "Valor do hotel (R$)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=f"hotel_value_{suffix}",
                )
        type_col, value_col = st.columns([2, 1])
        with type_col:
            benefit_type = st.selectbox(
                "Tipo da despesa",
                benefit_options,
                format_func=lambda value: benefit_option_labels[value],
                key=f"benefit_{suffix}",
            )
        with value_col:
            if benefit_type != BenefitType.NONE.value:
                benefit_amount = fixed_benefit_values[benefit_type]
                st.text_input(
                    "Valor fixo",
                    value=format_brl(benefit_amount),
                    disabled=True,
                    key=f"fixed_benefit_{suffix}_{benefit_type}_{benefit_amount}",
                )
            else:
                benefit_amount = money(0)
        entries.append(
            {
                "date": day,
                "city": city,
                "hotel_name": hotel_name,
                "hotel_amount": money(hotel_amount),
                "benefit_type": benefit_type,
                "benefit_amount": money(benefit_amount),
            }
        )

st.subheader("Local do preenchimento")
location = st.text_input(
    "Cidade/UF",
    max_chars=80,
    placeholder="Ex.: Divinópolis/MG",
    key=f"location_{context}",
)

totals = calculate_rdv_totals(entries, advance_value)
st.subheader("Resumo do RDV")
metric_columns = st.columns(4)
metric_columns[0].metric("Diárias", format_brl(totals["daily_total"]))
metric_columns[1].metric("Tickets", format_brl(totals["ticket_total"]))
metric_columns[2].metric("Hotéis (informativo)", format_brl(totals["hotel_total"]))
metric_columns[3].metric("Total da quinzena", format_brl(totals["expense_total"]))
if advance_answer == "Sim":
    st.metric(
        "Adiantamento recebido (informativo)",
        format_brl(totals["advance_total"]),
    )
st.caption(
    "O total da quinzena considera somente diárias e tickets. Hotéis e adiantamento não entram no cálculo."
)

st.subheader("Prévia da folha")
st.caption(
    "Esta é a folha como está ficando. Ela é atualizada conforme você preenche os campos."
)
preview_entries = [
    SimpleNamespace(
        date=entry["date"],
        city=entry["city"],
        hotel_name=entry["hotel_name"],
        hotel_amount=entry["hotel_amount"],
        benefit_type=BenefitType(str(entry["benefit_type"])),
        benefit_amount=entry["benefit_amount"],
    )
    for entry in entries
]
preview_rdv = SimpleNamespace(
    id=existing.id if existing else 0,
    employee=employee,
    period=period,
    advance_received=advance_answer == "Sim",
    advance_amount=money(advance_value),
    entries=preview_entries,
    location=location.strip().upper(),
)
preview_png = pdf_to_png(rdv_to_pdf(preview_rdv), scale=1.5)
st.image(preview_png, use_container_width=True)

# Streamlit reruns this page after a widget is committed (for text fields, on
# Enter or when focus leaves the field). Compare the current payload with the
# previous render so normal reruns do not generate unnecessary database writes.
draft_fingerprint = (
    advance_answer == "Sim",
    str(money(advance_value)),
    location.strip(),
    tuple(
        (
            entry["date"].isoformat(),
            str(entry["city"]),
            str(entry["hotel_name"]),
            str(entry["hotel_amount"]),
            str(entry["benefit_type"]),
            str(entry["benefit_amount"]),
        )
        for entry in entries
    ),
)
fingerprint_key = f"rdv_draft_fingerprint_{context}"
saved_at_key = f"rdv_draft_saved_at_{context}"
if fingerprint_key not in st.session_state:
    st.session_state[fingerprint_key] = draft_fingerprint
    if existing and existing.status == SubmissionStatus.RASCUNHO:
        st.session_state[saved_at_key] = existing.updated_at
elif st.session_state[fingerprint_key] != draft_fingerprint:
    has_draft_data = (
        advance_answer == "Sim"
        or bool(location.strip())
        or any(
            entry["city"]
            or entry["hotel_name"]
            or entry["hotel_amount"]
            or entry["benefit_type"] != BenefitType.NONE.value
            or entry["benefit_amount"]
            for entry in entries
        )
    )
    can_update_existing = bool(
        existing
        and existing.status
        in {SubmissionStatus.RASCUNHO, SubmissionStatus.REJEITADO}
    )
    if has_draft_data or can_update_existing:
        try:
            draft = save_rdv_draft(
                employee.id,
                period.id,
                advance_answer == "Sim",
                advance_value,
                entries,
                location,
            )
            st.session_state[fingerprint_key] = draft_fingerprint
            st.session_state[saved_at_key] = draft.updated_at
        except BusinessError as exc:
            st.warning(f"Não foi possível salvar o rascunho: {exc}")
        except Exception:
            logger.exception("Falha inesperada ao salvar rascunho RDV")
            st.warning(
                "Não foi possível salvar o rascunho agora. "
                "Seus dados continuam nesta tela; tente novamente."
            )
    else:
        st.session_state[fingerprint_key] = draft_fingerprint

if saved_at := st.session_state.get(saved_at_key):
    st.success(
        f"Rascunho salvo automaticamente às {format_datetime(saved_at)[-5:]}. "
        "Você pode sair e continuar depois."
    )
else:
    st.caption(
        "Suas alterações serão salvas automaticamente. O RDV só será enviado "
        "ao analista quando você confirmar o envio no final."
    )

if st.button(
    "ENVIAR RDV",
    type="primary",
    disabled=not location.strip(),
    use_container_width=True,
):
    st.session_state["rdv_confirm"] = True

if st.session_state.get("rdv_confirm"):
    st.warning("Confirmar o envio deste RDV?")
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button(
        "SIM, ENVIAR", type="primary", use_container_width=True
    ):
        try:
            saved = create_rdv(
                employee.id,
                period.id,
                advance_answer == "Sim",
                advance_value,
                entries,
                location,
            )
            st.session_state["rdv_success"] = protocol(saved.id)
            st.session_state["rdv_success_context"] = base_context
            st.session_state["rdv_confirm"] = False
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))
        except Exception:
            logger.exception("Falha inesperada ao enviar RDV")
            st.error(
                "Não foi possível enviar o RDV. Tente novamente ou procure o responsável pela frota."
            )
    if cancel_col.button("NÃO", use_container_width=True):
        st.session_state["rdv_confirm"] = False
        st.rerun()
