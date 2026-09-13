"""Convite de usuário do escritório (Hub) por e-mail."""

from __future__ import annotations

import logging
import secrets
import string

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def generate_temporary_password(*, length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(8, length)))


def send_tenant_invite_email(
    *,
    tenant,
    user,
    role_label: str,
    hub_login_url: str,
    temporary_password: str = "",
    actor_name: str = "",
) -> bool:
    """
    Envia instruções de acesso ao Hub.
    Returns True se o backend reportou envio.
    Raises Exception em falha SMTP (caller trata com mensagem).
    """
    to_email = (getattr(user, "email", None) or "").strip()
    if not to_email or "@" not in to_email:
        return False

    office = tenant.legal_name or tenant.slug
    subject = f"Convite EXEQ Hub — {office}"
    lines = [
        f"Olá{(' ' + user.name) if user.name else ''},",
        "",
        f"Você foi convidado(a) para o escritório «{office}» no EXEQ Hub.",
        f"Papel: {role_label}.",
        f"Empresa / tenant (slug no login): {tenant.slug}",
        f"E-mail de login: {to_email}",
    ]
    if temporary_password:
        lines.extend(
            [
                f"Senha inicial: {temporary_password}",
                "",
                "Altere a senha após o primeiro acesso (quando o fluxo estiver disponível).",
            ]
        )
    else:
        lines.append(
            "Use a senha já conhecida desta conta (vínculo a um usuário existente).",
        )
    if actor_name:
        lines.append(f"Convidado por: {actor_name}.")
    lines.extend(
        [
            "",
            f"Acesse: {hub_login_url}",
            "",
            "— EXEQ Hub",
        ]
    )
    body = "\n".join(lines)
    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(settings, "SERVER_EMAIL", None)
        or "noreply@exeq.local"
    )
    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[to_email],
    )
    sent = msg.send(fail_silently=False)
    if not sent:
        raise RuntimeError("Backend de e-mail retornou 0 enviados.")
    logger.info(
        "tenant_invite_email_sent tenant=%s email=%s",
        tenant.slug,
        to_email,
    )
    return True
