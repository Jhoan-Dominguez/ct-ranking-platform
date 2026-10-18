"""Envío de correos de la app (códigos de verificación y avisos de cuenta).

Los correos de Keycloak (verificación de cuenta y configuración de 2FA) los envía Keycloak con su
propio SMTP; ambos usan el mismo servidor (Mailpit en desarrollo).

``MAIL_BACKEND=memory`` guarda los mensajes en ``OUTBOX`` en lugar de enviarlos (pruebas).
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from app.config import get_settings


class MailError(RuntimeError):
    pass


@dataclass
class SentMail:
    to: str
    subject: str
    text: str


OUTBOX: list[SentMail] = []


def _html(title: str, paragraphs: list[str]) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        '<div style="font-family:sans-serif;max-width:520px;margin:auto;color:#1f2937">'
        f'<h2 style="color:#4F46E5">{escape(title)}</h2>{body}'
        '<p style="color:#6b7280;font-size:12px">CT Ranking · Este es un mensaje automático.</p>'
        "</div>"
    )


def send(to: str, subject: str, paragraphs: list[str]) -> None:
    """Envía un correo de texto + HTML. Los párrafos ya deben venir escapados para HTML."""
    settings = get_settings()
    text = "\n\n".join(p.replace("<b>", "").replace("</b>", "") for p in paragraphs)
    if settings.mail_backend == "memory":
        OUTBOX.append(SentMail(to=to, subject=subject, text=text))
        return
    message = EmailMessage()
    message["From"] = formataddr((settings.mail_from_name, settings.mail_from))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(_html(subject, paragraphs), subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(
            "No fue posible enviar el correo. Verifica la configuración SMTP (`make up`)."
        ) from exc
