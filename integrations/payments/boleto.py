"""Extrai artefatos de boleto/BolePix a partir da resposta do gateway."""

from __future__ import annotations

from typing import Any


def extract_boleto_artifacts(raw: dict[str, Any] | None) -> dict[str, str]:
    """
    Normaliza campos comuns de Asaas / Inter / C6 / stub.

    Retorna chaves: payment_url, digitable_line, barcode, boleto_pdf_url, pix_copy_paste.
    """
    data = raw or {}
    payment_url = _first_str(
        data,
        "bankSlipUrl",
        "invoiceUrl",
        "paymentUrl",
        "payment_url",
        "url",
        "link",
    )
    digitable_line = _first_str(
        data,
        "identificationField",
        "linhaDigitavel",
        "digitable_line",
        "digitableLine",
        "linha_digitavel",
    )
    barcode = _first_str(
        data,
        "barCode",
        "barcode",
        "codigoBarras",
        "codigo_barras",
    )
    boleto_pdf_url = _first_str(
        data,
        "bankSlipUrl",
        "pdfUrl",
        "pdf_url",
        "boletoPdfUrl",
        "boleto_pdf_url",
    )
    pix = data.get("pix")
    pix_copy = ""
    if isinstance(pix, dict):
        pix_copy = _first_str(pix, "payload", "emv", "copiaECola", "qrCode")
    if not pix_copy:
        pix_copy = _first_str(
            data,
            "pixCopiaECola",
            "pix_copy_paste",
            "pixCopyPaste",
            "qrCodePayload",
        )
    return {
        "payment_url": payment_url,
        "digitable_line": digitable_line,
        "barcode": barcode,
        "boleto_pdf_url": boleto_pdf_url or payment_url,
        "pix_copy_paste": pix_copy,
    }


def stub_boleto_artifacts(*, provider: str, external_ref: str) -> dict[str, str]:
    """Artefatos determinísticos para modo stub (QA sem gateway real)."""
    digits = "".join(ch for ch in external_ref if ch.isdigit()) or "00000000000"
    line = f"23793.38128 60000.000003 00000.000400 1 {digits.zfill(14)[:14]}"
    return {
        "payment_url": f"https://stub.exeq.local/{provider}/boleto/{external_ref}",
        "digitable_line": line,
        "barcode": f"23791{digits.zfill(39)[:39]}",
        "boleto_pdf_url": f"https://stub.exeq.local/{provider}/boleto/{external_ref}.pdf",
        "pix_copy_paste": "",
    }


def _first_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
