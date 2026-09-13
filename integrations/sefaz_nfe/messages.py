"""Mensagens amigáveis — falhas de transporte HTTP/mTLS SEFAZ."""

from __future__ import annotations

import re
from typing import Any


def _is_ssl_error(text: str) -> bool:
    t = text.lower()
    return (
        "sslcertverificationerror" in t
        or "certificate verify failed" in t
        or "ssl: certificate_verify_failed" in t
        or "ssLError".lower() in t and "certificate" in t
    )


def _is_timeout(text: str) -> bool:
    t = text.lower()
    return "timed out" in t or "timeout" in t


def _is_connection(text: str) -> bool:
    t = text.lower()
    return (
        "connection refused" in t
        or "failed to establish a new connection" in t
        or "name or service not known" in t
        or "getaddrinfo failed" in t
    )


def format_sefaz_transport_error(exc: BaseException, *, document_label: str = "NF-e") -> str:
    """
    Converte exceção de rede/SSL em texto para operador (sem stack trace).
    """
    raw = str(exc or "").strip()
    if not raw:
        return (
            f"Não foi possível enviar a {document_label} à SEFAZ. "
            "Tente novamente em instantes ou fale com o contador responsável."
        )

    if _is_ssl_error(raw):
        host = ""
        m = re.search(r"host='([^']+)'", raw, re.I)
        if m:
            host = m.group(1)
        where = f" ({host})" if host else ""
        return (
            f"Não foi possível conectar com segurança à SEFAZ{where}: "
            "falha na validação do certificado do servidor (cadeia ICP-Brasil). "
            "Peça ao responsável técnico para atualizar a cadeia de certificados "
            "ICP-Brasil v10 no servidor ou informe o suporte EXEQ."
        )

    if _is_timeout(raw):
        return (
            f"A SEFAZ não respondeu a tempo ao enviar a {document_label}. "
            "Verifique a internet do servidor e tente novamente."
        )

    if _is_connection(raw):
        return (
            f"Não foi possível alcançar a SEFAZ para autorizar a {document_label}. "
            "Verifique conexão de rede, firewall ou indisponibilidade do webservice."
        )

    if len(raw) > 220:
        raw = raw[:217] + "…"
    return (
        f"Falha de comunicação com a SEFAZ ao enviar a {document_label}: {raw}"
    )


def format_sefaz_http_rejection(
    rejection_code: str | None,
    rejection_message: str | None,
    *,
    document_label: str = "NF-e",
) -> str:
    """Normaliza mensagem já persistida (legado técnico ou nova amigável)."""
    code = (rejection_code or "").strip().upper()
    msg = (rejection_message or "").strip()
    if not msg:
        return f"A SEFAZ não concluiu a autorização da {document_label}."

    if code == "HTTP" and (
        msg.startswith("Falha HTTP SEFAZ")
        or "HTTPSConnectionPool" in msg
        or "SSLCertVerificationError" in msg
    ):
        # Mensagens antigas gravadas antes do formatter
        fake_exc = msg.split(":", 1)[-1].strip() if ":" in msg else msg
        if "Falha HTTP" in msg and "(" in msg:
            fake_exc = msg[msg.find("(") :]
        return format_sefaz_transport_error(
            Exception(fake_exc if fake_exc else msg),
            document_label=document_label,
        )

    if code == "HTTP" and not msg.startswith("Falha HTTP"):
        return msg

    if msg.startswith("Falha HTTP SEFAZ"):
        return format_sefaz_transport_error(
            Exception(msg.split(":", 1)[-1].strip()),
            document_label=document_label,
        )

    if code == "209" or "ie do emitente" in msg.lower():
        return (
            f"A SEFAZ rejeitou a Inscrição Estadual (IE) do emitente na {document_label}. "
            "Atualize em Cadastro → Empresas com a IE numérica cadastrada na SEFAZ "
            "(desmarque Isento de IE se a empresa possui IE ativa)."
        )

    return msg
