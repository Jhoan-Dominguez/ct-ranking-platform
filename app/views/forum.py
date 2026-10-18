"""Foros de discusión."""

from __future__ import annotations

import streamlit as st

from app.db.session import session_scope
from app.services import forum, social
from app.ui import common


@st.dialog("Nueva publicación", width="large")
def _new_post_dialog(user_id: int) -> None:
    with st.form("new_post"):
        title = st.text_input("Título", max_chars=200)
        category = st.selectbox("Categoría", forum.CATEGORIES)
        body = st.text_area(
            "Describe la problemática, duda o tema", height=200, help="Admite Markdown."
        )
        tags = st.text_input("Etiquetas (separadas por coma)", placeholder="cálculo, parcial")
        if st.form_submit_button("Publicar", type="primary"):

            def _create(s):
                post = forum.create_post(
                    s, user_id, title=title, body=body, category=category, tags=tags
                )
                st.session_state["post_id"] = post.id

            common.run_action(_create, "Publicación creada")


def _post_list(user) -> None:
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    search = c1.text_input("Buscar", placeholder="Título, contenido o etiqueta…")
    category = c2.selectbox("Categoría", ["Todas", *forum.CATEGORIES])
    status = c3.selectbox("Estado", ["Todas", "Abiertas", "Resueltas"])
    order = c4.selectbox("Orden", list(forum.ORDERINGS))
    only_following = st.toggle("Sólo de personas que sigo")

    with session_scope() as s:
        rows = forum.list_posts(
            s,
            search=search,
            category=None if category == "Todas" else category,
            solved={"Todas": None, "Abiertas": False, "Resueltas": True}[status],
            author_ids=social.following_ids(s, user.id) if only_following else None,
            order=forum.ORDERINGS[order],
        )
        if not rows:
            st.info("No hay publicaciones con esos filtros. ¡Crea la primera!")
        for row in rows:
            p = row.post
            with st.container(border=True):
                left, right = st.columns([5, 1], vertical_alignment="center")
                with left:
                    st.markdown(
                        f"### {'✅ ' if p.is_solved else ''}{p.title}\n"
                        f":blue-badge[{p.category}] "
                        + " ".join(f":gray-badge[#{t}]" for t in p.tags.split(",") if t)
                    )
                    common.user_chip(
                        p.author,
                        26,
                        f"{common.fmt_dt(p.created_at)} · {row.comments} 💬 · {row.likes} 👍",
                    )
                if right.button("Abrir", key=f"open_{p.id}", width="stretch"):
                    st.session_state["post_id"] = p.id
                    st.rerun()


def _post_detail(user, post_id: int) -> None:
    if st.button("← Volver a los foros"):
        st.session_state.pop("post_id", None)
        st.rerun()

    with session_scope() as s:
        post = forum.get_post(s, post_id)
        if post is None:
            st.session_state.pop("post_id", None)
            st.warning("La publicación ya no existe.")
            return
        liked = any(like.user_id == user.id for like in post.likes)
        can_moderate = user.is_admin or user.id == post.author_id

        st.title(("✅ " if post.is_solved else "") + post.title)
        st.markdown(
            f":blue-badge[{post.category}] "
            + " ".join(f":gray-badge[#{t}]" for t in post.tags.split(",") if t)
        )
        common.user_chip(post.author, 36, common.fmt_dt(post.created_at))
        with st.container(border=True):
            st.markdown(post.body)

        actions = st.columns([1, 1, 1, 3])
        if actions[0].button(
            f"{'💙' if liked else '👍'} {len(post.likes)}", help="Me gusta", key="like"
        ):
            common.run_action(lambda s2: forum.toggle_like(s2, post_id, user.id))
        if can_moderate:
            label = "Reabrir" if post.is_solved else "Marcar resuelta"
            if actions[1].button(label, icon="✅"):
                common.run_action(
                    lambda s2: forum.set_solved(s2, user, post_id, not post.is_solved),
                    "Estado actualizado",
                )
            if actions[2].button("Eliminar", icon="🗑️"):
                st.session_state.pop("post_id", None)
                common.run_action(lambda s2: forum.delete_post(s2, user, post_id), "Eliminada")

        st.subheader(f"💬 Comentarios ({len(post.comments)})")
        for c in post.comments:
            with st.container(border=True):
                head, tail = st.columns([6, 1])
                with head:
                    common.user_chip(c.author, 28, common.fmt_dt(c.created_at))
                    st.markdown(c.body)
                if (user.is_admin or user.id == c.author_id) and tail.button(
                    "🗑️", key=f"del_c_{c.id}", help="Eliminar comentario"
                ):
                    common.run_action(
                        lambda s2, cid=c.id: forum.delete_comment(s2, user, cid), "Eliminado"
                    )

    with st.form("comment", clear_on_submit=True):
        body = st.text_area("Escribe una respuesta o comentario", height=120)
        if st.form_submit_button("Comentar", type="primary"):
            common.run_action(lambda s: forum.add_comment(s, post_id, user.id, body), "Comentado")


def render() -> None:
    user = common.require_user()
    post_id = st.session_state.get("post_id")
    if post_id:
        _post_detail(user, post_id)
        return
    head, button = st.columns([4, 1], vertical_alignment="bottom")
    head.title("💬 Foros de discusión")
    if button.button("Nueva publicación", icon="✏️", type="primary", width="stretch"):
        _new_post_dialog(user.id)
    _post_list(user)
