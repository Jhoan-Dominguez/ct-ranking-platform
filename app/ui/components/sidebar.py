"""Menú lateral: expandir al pasar el mouse cuando está oculto (ver assets/sidebar_hover.js)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import streamlit as st

ASSET = Path(__file__).resolve().parent.parent / "assets" / "sidebar_hover.js"


@cache
def _sidebar_hover_script() -> str:
    return ASSET.read_text(encoding="utf-8")


def enable_sidebar_hover() -> None:
    """Expande la barra lateral oculta al pasar el mouse por el borde izquierdo
    (ver app/ui/assets/sidebar_hover.js). Debe llamarse dentro de ``with st.sidebar``."""
    st.html(f"<script>{_sidebar_hover_script()}</script>", unsafe_allow_javascript=True)
