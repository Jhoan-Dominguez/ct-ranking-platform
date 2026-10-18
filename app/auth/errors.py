"""Errores de autenticación con mensajes aptos para mostrar al usuario."""

from __future__ import annotations


class AuthError(Exception):
    """Error con mensaje apto para mostrar al usuario."""


class EmailNotVerifiedError(AuthError):
    """Credenciales correctas, pero la cuenta aún no se activó con el enlace del correo."""

    def __init__(self, login: str) -> None:
        super().__init__(
            "Tu cuenta aún no está activada. Abre el enlace que te enviamos por correo "
            "(revisa también la carpeta de spam)."
        )
        self.login = login


class AccountNotFoundError(AuthError):
    """Inicio de sesión con Google de alguien que aún no tiene cuenta en la plataforma."""

    def __init__(self, email: str) -> None:
        super().__init__(
            f"No existe una cuenta en CT Ranking para {email}. Créala primero en la pestaña "
            "«Crear cuenta» (puedes usar «Crear cuenta con Google»)."
        )
        self.email = email


INVALID_LOGIN = "Usuario, contraseña o código de verificación incorrectos."
