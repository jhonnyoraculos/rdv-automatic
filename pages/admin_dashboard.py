from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_drawable_canvas import st_canvas

from auth import (
    AdminRole,
    current_admin_role,
    current_admin_username,
    switch_admin_role,
)
from exports import pdf_to_png, rdv_to_csv, rdv_to_pdf, rdv_to_xlsx, rdvs_to_xlsx
from models import EmployeeRole, SubmissionStatus
from services import (
    BusinessError,
    approve_rdv,
    dashboard_stats,
    delete_rdv,
    get_periods,
    get_rdv,
    get_rdvs,
    reject_rdv,
)
from ui import (
    company_header,
    require_admin,
    status_badge,
    submission_status_label,
)
from utils import (
    calculate_rdv_totals,
    format_brl,
    format_date,
    format_datetime,
    now_sp,
    protocol,
    signature_from_canvas,
)

require_admin()
admin_role = current_admin_role()
if admin_role is None:
    st.error("Sua sessão não possui um perfil válido. Saia e entre novamente.")
    st.stop()
admin_username = current_admin_username()
role_label = (
    "Analista de frota" if admin_role == AdminRole.ANALISTA else "Gestor de frota"
)
company_header(
    "Painel RDV", f"{role_label} — acompanhamento e aprovação dos relatórios"
)
if notice := st.session_state.pop("dashboard_notice", None):
    st.success(notice)
role_options = list(AdminRole)
selected_role = st.selectbox(
    "Perfil ativo para testes",
    role_options,
    index=role_options.index(admin_role),
    format_func=lambda role: (
        "Analista de frota" if role == AdminRole.ANALISTA else "Gestor de frota"
    ),
    key="test_role_switcher",
    help="Opção temporária para testar as duas etapas sem sair da conta.",
)
if selected_role != admin_role:
    switch_admin_role(selected_role)
    st.rerun()
st.caption(
    "Modo temporário de testes: troque o perfil acima para executar a etapa do analista ou do gestor."
)

periods = get_periods()
period_by_id = {period.id: period for period in periods}
period_filter = st.selectbox(
    "Período para os indicadores",
    [None, *period_by_id],
    format_func=lambda value: (
        "Todos os períodos"
        if value is None
        else (
            f"{format_date(period_by_id[value].start_date)} a {format_date(period_by_id[value].end_date)}"
            f"{' • ATIVO' if period_by_id[value].active else ''}"
        )
    ),
    key="dashboard_period",
)
stats = dashboard_stats(period_filter)
metric_cols = st.columns(5)
metric_cols[0].metric("Aguardando analista", stats["counts"]["ENVIADO"])
metric_cols[1].metric("Aguardando gestor", stats["counts"]["AGUARDANDO_GESTOR"])
metric_cols[2].metric("Concluídos", stats["counts"]["APROVADO"])
metric_cols[3].metric("Rejeitados", stats["counts"]["REJEITADO"])
metric_cols[4].metric("Total da quinzena", format_brl(stats["expense_total"]))
assigned_status = (
    SubmissionStatus.ENVIADO
    if admin_role == AdminRole.ANALISTA
    else SubmissionStatus.AGUARDANDO_GESTOR
)
pending = stats["counts"][assigned_status.value]
st.info(
    f"{pending} RDV{'s' if pending != 1 else ''} aguardando sua aprovação como {role_label.lower()}."
)

st.subheader("Relatórios")
with st.expander("Filtros", expanded=False):
    filter_cols = st.columns(3)
    search = filter_cols[0].text_input("Pesquisar colaborador")
    role_filter = filter_cols[1].selectbox(
        "Função",
        [None, *EmployeeRole],
        format_func=lambda x: "Todas" if x is None else x.value,
    )
    status_options = [None, *SubmissionStatus]
    status_filter = filter_cols[2].selectbox(
        "Status",
        status_options,
        index=0,
        format_func=lambda x: "Todos" if x is None else submission_status_label(x),
        key=f"dashboard_status_{admin_role.value}",
    )
    use_dates = st.checkbox("Filtrar pela data de envio")
    submitted_from = submitted_to = None
    if use_dates:
        today = now_sp().date()
        date_cols = st.columns(2)
        submitted_from = date_cols[0].date_input(
            "Enviado a partir de", value=today.replace(day=1)
        )
        submitted_to = date_cols[1].date_input("Enviado até", value=today)

rdvs = get_rdvs(
    period_id=period_filter,
    role=role_filter,
    status=status_filter,
    search=search,
    submitted_from=submitted_from,
    submitted_to=submitted_to,
)
rows = []
for rdv in rdvs:
    total = calculate_rdv_totals(rdv.entries, rdv.advance_amount)["expense_total"]
    rows.append(
        {
            "Protocolo": protocol(rdv.id),
            "Colaborador": rdv.employee.name,
            "Função": rdv.employee.role.value,
            "Período": f"{format_date(rdv.period.start_date)} a {format_date(rdv.period.end_date)}",
            "Total": format_brl(total),
            "Envio": format_datetime(rdv.submitted_at),
            "Status": submission_status_label(rdv.status),
        }
    )
rdv_table = pd.DataFrame(rows)
display_table = rdv_table
if not rdv_table.empty:
    status_colors = {
        "AGUARDANDO ANALISTA": "background-color: #fff1cc; color: #8a5b00; font-weight: 700",
        "AGUARDANDO GESTOR": "background-color: #dcecff; color: #154f8b; font-weight: 700",
        "CONCLUÍDO": "background-color: #dff6e8; color: #116b39; font-weight: 700",
        "REJEITADO": "background-color: #fde2e5; color: #a11427; font-weight: 700",
    }
    display_table = rdv_table.style.map(
        lambda value: status_colors.get(str(value), ""), subset=["Status"]
    )
table_event = st.dataframe(
    display_table,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key=f"rdv_list_table_{st.session_state.get('rdv_table_revision', 0)}",
)
if rdvs:
    st.caption("Clique em uma linha da tabela para abrir a folha do RDV.")
    st.download_button(
        "Baixar Excel dos resultados filtrados",
        data=rdvs_to_xlsx(rdvs),
        file_name="rdvs_filtrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.caption("Nenhum RDV encontrado com os filtros escolhidos.")

available_ids = [item.id for item in rdvs]
selected_id = st.session_state.get("opened_rdv_id")
selected_rows = table_event.selection.rows
if selected_rows:
    selected_id = rdvs[selected_rows[0]].id
    st.session_state["opened_rdv_id"] = selected_id
elif selected_id not in available_ids:
    selected_id = available_ids[0] if len(available_ids) == 1 else None
    st.session_state["opened_rdv_id"] = selected_id
if selected_id is None:
    st.stop()

rdv = get_rdv(selected_id)
if not rdv:
    st.error("RDV não encontrado.")
    st.stop()

st.divider()
st.subheader(f"{protocol(rdv.id)} — {rdv.employee.name}")
status_badge(rdv.status.value)
details_left, details_right = st.columns(2)
with details_left:
    st.write(f"**Função:** {rdv.employee.role.value}")
    st.write(
        f"**Período:** {format_date(rdv.period.start_date)} a {format_date(rdv.period.end_date)}"
    )
    st.write(f"**Data do envio:** {format_datetime(rdv.submitted_at)}")
    st.write(f"**Local informado:** {rdv.location or '—'}")
with details_right:
    st.write(
        f"**Adiantamento:** {'Sim' if rdv.advance_received else 'Não'} — {format_brl(rdv.advance_amount)}"
    )
    st.write(f"**Revisado em:** {format_datetime(rdv.reviewed_at)}")
    st.write(f"**Data da assinatura:** {format_date(rdv.signed_date)}")
    st.write(
        f"**Analista:** {rdv.analyst_username or 'Pendente'}"
        f" — {format_datetime(rdv.analyst_signed_at)}"
    )
    st.write(
        f"**Gestor:** {rdv.manager_username or 'Pendente'}"
        f" — {format_datetime(rdv.manager_signed_at)}"
    )
    if rdv.admin_comment:
        st.write(f"**Motivo da rejeição:** {rdv.admin_comment}")

pdf_data = rdv_to_pdf(rdv)
png_data = pdf_to_png(pdf_data)
st.subheader("Folha do RDV para conferência")
mobile_tab, pdf_tab = st.tabs(["Visualização para celular", "Visualização em PDF"])
with mobile_tab:
    st.image(png_data, use_container_width=True)
with pdf_tab:
    st.pdf(pdf_data, height=800, key=f"rdv_pdf_{rdv.id}_{rdv.updated_at}")

download_cols = st.columns(4)
download_cols[0].download_button(
    "Baixar PDF",
    pdf_data,
    f"rdv_{rdv.id:06d}.pdf",
    "application/pdf",
    use_container_width=True,
)
download_cols[1].download_button(
    "Baixar PNG",
    png_data,
    f"rdv_{rdv.id:06d}.png",
    "image/png",
    use_container_width=True,
)
download_cols[2].download_button(
    "Baixar Excel",
    rdv_to_xlsx(rdv),
    f"rdv_{rdv.id:06d}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
download_cols[3].download_button(
    "Baixar CSV",
    rdv_to_csv(rdv),
    f"rdv_{rdv.id:06d}.csv",
    "text/csv",
    use_container_width=True,
)

can_review = rdv.status == assigned_status
if can_review:
    st.subheader(f"Assinatura e aprovação — {role_label}")
    st.caption("Assine no quadro usando o mouse ou o dedo antes de aprovar.")
    approval_context = f"{admin_role.value}_{rdv.id}_{rdv.updated_at}"
    canvas_result = st_canvas(
        stroke_width=5,
        stroke_color="#172033",
        background_color="#FFFFFF",
        update_streamlit=True,
        height=300,
        width=320,
        drawing_mode="freedraw",
        return_image_data=True,
        key=f"approval_signature_{approval_context}",
    )
    signature_state_key = f"approval_signature_png_{approval_context}"
    current_signature = signature_from_canvas(canvas_result.image_data)
    if current_signature:
        st.session_state[signature_state_key] = current_signature
    elif canvas_result.image_data is not None:
        st.session_state.pop(signature_state_key, None)
    approval_signature = st.session_state.get(signature_state_key)
    if approval_signature:
        st.success("Assinatura registrada. O RDV está pronto para sua aprovação.")
    else:
        st.caption("A assinatura é obrigatória para aprovar.")

    action_cols = st.columns(2)
    if action_cols[0].button(
        "ASSINAR E APROVAR",
        type="primary",
        disabled=approval_signature is None,
        use_container_width=True,
    ):
        try:
            approved = approve_rdv(
                rdv.id, admin_role.value, approval_signature, admin_username
            )
            if approved.status == SubmissionStatus.AGUARDANDO_GESTOR:
                st.success("RDV assinado pelo analista e enviado ao gestor.")
            else:
                st.session_state[f"dashboard_status_{admin_role.value}"] = None
                st.session_state["opened_rdv_id"] = rdv.id
                st.success("RDV assinado pelo gestor e concluído.")
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))
    with action_cols[1]:
        with st.form(f"reject_{rdv.id}_{admin_role.value}"):
            reason = st.text_area("Motivo obrigatório para rejeitar", max_chars=1000)
            reject = st.form_submit_button("REJEITAR RDV", use_container_width=True)
        if reject:
            try:
                reject_rdv(rdv.id, reason, admin_role.value)
                st.success("RDV rejeitado e liberado para correção do colaborador.")
                st.rerun()
            except BusinessError as exc:
                st.error(str(exc))
elif rdv.status in (
    SubmissionStatus.ENVIADO,
    SubmissionStatus.AGUARDANDO_GESTOR,
):
    st.info(f"Este RDV está na etapa: {submission_status_label(rdv.status).lower()}.")

with st.expander("Excluir esta folha para o colaborador refazer", expanded=False):
    st.warning(
        "A exclusão remove a folha e todas as assinaturas. O colaborador poderá preencher e enviar um novo RDV para esta quinzena."
    )
    delete_confirmed = st.checkbox(
        "Confirmo que desejo excluir definitivamente esta folha.",
        key=f"delete_confirmed_{rdv.id}_{rdv.updated_at}",
    )
    if st.button(
        "EXCLUIR FOLHA E LIBERAR NOVO PREENCHIMENTO",
        type="primary",
        disabled=not delete_confirmed,
        use_container_width=True,
        key=f"delete_rdv_{rdv.id}",
    ):
        try:
            deleted_protocol = protocol(rdv.id)
            delete_rdv(rdv.id, admin_role.value, admin_username)
            st.session_state.pop("opened_rdv_id", None)
            st.session_state["rdv_table_revision"] = (
                st.session_state.get("rdv_table_revision", 0) + 1
            )
            st.session_state["dashboard_notice"] = (
                f"{deleted_protocol} excluído. O colaborador já pode refazer a folha."
            )
            st.rerun()
        except BusinessError as exc:
            st.error(str(exc))

with st.expander("Ver lançamentos e totais detalhados"):
    entry_rows = [
        {
            "Data": format_date(entry.date),
            "Cidade": entry.city or "—",
            "Hotel": entry.hotel_name or "—",
            "Valor hotel": format_brl(entry.hotel_amount),
            "Tipo": {"NONE": "Nenhum", "DIARIA": "Diária", "TICKET": "Ticket"}[
                entry.benefit_type.value
            ],
            "Valor": format_brl(entry.benefit_amount),
        }
        for entry in rdv.entries
    ]
    st.dataframe(pd.DataFrame(entry_rows), use_container_width=True, hide_index=True)
    totals = calculate_rdv_totals(rdv.entries, rdv.advance_amount)
    total_cols = st.columns(3)
    total_cols[0].metric("Total diária", format_brl(totals["daily_total"]))
    total_cols[1].metric("Total ticket", format_brl(totals["ticket_total"]))
    total_cols[2].metric("Total hotel (informativo)", format_brl(totals["hotel_total"]))
    total_cols = st.columns(2)
    total_cols[0].metric("Total da quinzena", format_brl(totals["expense_total"]))
    total_cols[1].metric(
        "Adiantamento (informativo)", format_brl(totals["advance_total"])
    )
    st.caption("O total da quinzena considera somente diárias e tickets.")
