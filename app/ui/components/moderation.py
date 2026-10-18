"""Componentes de interfaz para reportar y bloquear usuarios."""

from __future__ import annotations

import streamlit as st

from app.database.models import ReportReason
from app.services import moderation
from app.ui.components import actions


@st.dialog("Reportar")
def report_dialog(
    reporter_id: int,
    reported_id: int,
    reported_name: str,
    post_id: int | None = None,
    comment_id: int | None = None,
) -> None:
    if post_id:
        target = "esta publicación"
    elif comment_id:
        target = "este comentario"
    else:
        target = "a esta persona"
    st.markdown(f"Vas a reportar {target} de **{reported_name}**.")
    st.caption("El equipo de administración revisará el reporte. Quien reportas no lo sabrá.")
    with st.form("report_form"):
        reason = st.selectbox(
            "Motivo", list(ReportReason), format_func=lambda r: moderation.REASON_LABELS[r]
        )
        description = st.text_area(
            "Detalles (obligatorio si eliges «Otro motivo»)", max_chars=2000, height=110
        )
        also_block = st.checkbox(f"Bloquear también a {reported_name}")
        if st.form_submit_button("Enviar reporte", type="primary", icon="🚩"):

            def _report(s):
                moderation.report(
                    s,
                    reporter_id,
                    reported_id,
                    reason=reason,
                    description=description,
                    post_id=post_id,
                    comment_id=comment_id,
                )
                if also_block:
                    moderation.block(s, reporter_id, reported_id)

            actions.run_action(_report, "Reporte enviado. ¡Gracias por avisarnos!")


@st.dialog("Bloquear usuario")
def block_dialog(blocker_id: int, blocked_id: int, blocked_name: str) -> None:
    st.markdown(f"¿Bloquear a **{blocked_name}**?")
    st.markdown(
        "- Ninguno de los dos verá las publicaciones, comentarios, mensajes ni el perfil "
        "del otro.\n"
        "- Se eliminarán los seguimientos entre ustedes y no podrán volver a seguirse ni "
        "enviarse mensajes de apoyo.\n"
        "- Puedes desbloquearlo cuando quieras desde **Personas → Bloqueados**."
    )
    if st.button("Bloquear", type="primary", icon="🚫"):
        actions.run_action(
            lambda s: moderation.block(s, blocker_id, blocked_id),
            f"Bloqueaste a {blocked_name}",
        )


def actions_menu(me_id: int, person_id: int, person_name: str, key: str, **content) -> None:
    """Menú «⋯» con Reportar y Bloquear. ``content`` acepta post_id / comment_id."""
    with st.popover(
        "Más", icon=":material/more_horiz:", help="Reportar o bloquear", key=f"more_{key}"
    ):
        if st.button("Reportar", key=f"rep_{key}", icon="🚩", width="stretch"):
            report_dialog(me_id, person_id, person_name, **content)
        if st.button("Bloquear", key=f"blk_{key}", icon="🚫", width="stretch"):
            block_dialog(me_id, person_id, person_name)
