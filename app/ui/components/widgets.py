"""Widgets reutilizables: avatares, chip de usuario y campo de correo institucional."""

from __future__ import annotations

import base64
import hashlib

import streamlit as st

from app import auth
from app.database.models import User


def _initials_svg(user: User, size: int) -> str:
    initials = "".join(p[0] for p in (user.first_name, user.last_name) if p).upper() or "?"
    hue = int(hashlib.md5(user.username.encode()).hexdigest()[:2], 16) * 360 // 256
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
        f'<circle cx="50%" cy="50%" r="50%" fill="hsl({hue},55%,45%)"/>'
        f'<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" '
        f'font-family="sans-serif" font-size="{size * 0.4:.0f}" fill="#fff">{initials}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def avatar_src(user: User, size: int = 48) -> str:
    if user.avatar:
        return (
            f"data:{user.avatar_mime or 'image/png'};base64,"
            + base64.b64encode(user.avatar).decode()
        )
    return _initials_svg(user, size)


def avatar_html(user: User, size: int = 40) -> str:
    return (
        f'<img src="{avatar_src(user, size)}" width="{size}" height="{size}" '
        f'style="border-radius:50%;object-fit:cover;vertical-align:middle" alt="">'
    )


def user_chip(user: User, size: int = 32, subtitle: str = "") -> None:
    sub = f'<br><span style="opacity:.65;font-size:.85em">{subtitle}</span>' if subtitle else ""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:.6rem">{avatar_html(user, size)}'
        f"<div><b>{_escape(user.display_name)}</b> "
        f'<span style="opacity:.6">@{_escape(user.username)}</span>{sub}</div></div>',
        unsafe_allow_html=True,
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def institutional_email_input(label: str, value: str = "", key: str | None = None) -> str:
    """Campo para la parte del correo antes de la @: el dominio institucional es fijo.
    Devuelve sólo la parte local (``auth.student_email`` arma y valida el correo completo)."""
    domain = auth.student_domain()
    local_value = value.split("@", 1)[0] if value.endswith("@" + domain) else ""
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    local = left.text_input(
        label, local_value, key=key, placeholder="nombre.apellido", help=f"Tu correo @{domain}"
    )
    right.markdown(f"**@{domain}**")
    return local
