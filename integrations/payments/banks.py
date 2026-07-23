"""Gateway bancário enxuto — stub (default) ou HTTP (Inter Cobrança v3 / C6 bank_slips)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import httpx
from django.conf import settings

from integrations.payments.boleto import stub_boleto_artifacts
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.inter_auth import InterAuthClient
from integrations.payments.inter_cancel import (
    DEFAULT_INTER_CANCEL_MOTIVO,
    INTER_CANCEL_MOTIVOS,
)
from integrations.payments.inter_status import (
    inter_artifacts,
    map_inter_situacao,
)
from integrations.payments.port import ChargeRegisterResult


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _tipo_pessoa(document: str) -> str:
    return "JURIDICA" if len(_digits(document)) > 11 else "FISICA"


_IBGE_CIDADE = {
    "3504107": "ATIBAIA",
}


def _inter_cidade(addr: dict) -> str:
    cidade = (addr.get("cidade") or addr.get("municipio") or "").strip()
    if cidade:
        return cidade[:60]
    ibge = str(addr.get("codigo_municipio") or addr.get("ibge") or "")
    return (_IBGE_CIDADE.get(ibge) or "SAO PAULO")[:60]


class BankPaymentGateway:
    """Porta PaymentGateway para bancos com API REST + Bearer token."""

    def __init__(
        self,
        *,
        kind: str,
        token: str | None = None,
        base_url: str | None = None,
        mode: str | None = None,
        timeout: float = 30.0,
    ):
        self.kind = kind
        self.token = token or ""
        self.base_url = (base_url or "").rstrip("/")
        self.mode = (mode or settings.PAYMENT_HTTP_MODE or "stub").lower()
        self.timeout = timeout

    def registrar_cobranca(
        self,
        *,
        amount_cents: int,
        due_date: date,
        description: str,
        customer_document: str,
        customer_name: str,
        external_reference: str,
        idempotency_key: str,
        customer_address: dict[str, Any] | None = None,
        customer_email: str = "",
        charge_options: dict[str, Any] | None = None,
    ) -> ChargeRegisterResult:
        if self.mode != "http":
            ref = f"{self.kind}_{uuid4().hex[:16]}"
            arts = stub_boleto_artifacts(provider=self.kind, external_ref=ref)
            return ChargeRegisterResult(
                external_ref=ref,
                status="registered",
                raw={
                    "provider": self.kind,
                    "mode": "stub",
                    "action": "registrar",
                    "externalReference": external_reference,
                    "idempotency_key": idempotency_key,
                    "amount_cents": amount_cents,
                    "due_date": due_date.isoformat(),
                    "charge_options": charge_options or {},
                },
                digitable_line=arts["digitable_line"],
                barcode=arts["barcode"],
                payment_url=arts["payment_url"],
                boleto_pdf_url=arts["boleto_pdf_url"],
                pix_copy_paste=arts.get("pix_copy_paste") or "",
            )

        body = self._charge_body(
            amount_cents=amount_cents,
            due_date=due_date,
            description=description,
            customer_document=customer_document,
            customer_name=customer_name,
            external_reference=external_reference,
            customer_address=customer_address,
            customer_email=customer_email,
            charge_options=charge_options,
        )
        data = self._request(
            "POST",
            self._charge_path(),
            json=body,
            headers=self._extra_headers(idempotency_key=idempotency_key),
        )
        ref = self._extract_ref(data)
        if not ref:
            raise PaymentGatewayError(f"{self.kind} sem id na resposta: {data}")
        # Inter frequentemente só devolve codigoSolicitacao; extrair o que houver.
        arts = inter_artifacts(data) if self.kind == "inter" else {}
        from integrations.payments.boleto import extract_boleto_artifacts

        fallback = extract_boleto_artifacts(data if isinstance(data, dict) else {})
        return ChargeRegisterResult(
            external_ref=ref,
            status="registered",
            raw={"provider": self.kind, "mode": "http", **data},
            digitable_line=str(
                arts.get("digitable_line") or fallback.get("digitable_line") or ""
            ),
            barcode=str(arts.get("barcode") or fallback.get("barcode") or ""),
            pix_copy_paste=str(
                arts.get("pix_copy_paste") or fallback.get("pix_copy_paste") or ""
            ),
            payment_url=str(fallback.get("payment_url") or ""),
            boleto_pdf_url=str(fallback.get("boleto_pdf_url") or ""),
            extras=arts or fallback,
        )

    def cancelar(
        self, *, ref: str, motivo_cancelamento: str | None = None
    ) -> ChargeRegisterResult:
        if self.mode != "http":
            return ChargeRegisterResult(
                external_ref=ref,
                status="cancelled",
                raw={
                    "provider": self.kind,
                    "mode": "stub",
                    "action": "cancelar",
                    "ref": ref,
                    "motivo_cancelamento": motivo_cancelamento,
                },
            )
        method, path, body = self._cancel_spec(ref, motivo_cancelamento=motivo_cancelamento)
        data = self._request(method, path, json=body) if body is not None else self._request(method, path)
        return ChargeRegisterResult(
            external_ref=ref,
            status="cancelled",
            raw={"provider": self.kind, "mode": "http", **(data if isinstance(data, dict) else {})},
        )

    def consultar_cobranca(self, *, ref: str) -> ChargeRegisterResult:
        if self.mode != "http":
            arts = stub_boleto_artifacts(provider=self.kind, external_ref=ref)
            return ChargeRegisterResult(
                external_ref=ref,
                status="registered",
                raw={
                    "provider": self.kind,
                    "mode": "stub",
                    "action": "consultar",
                    "ref": ref,
                    "cobranca": {
                        "codigoSolicitacao": ref,
                        "situacao": "A_RECEBER",
                        "boleto": {
                            "linhaDigitavel": arts["digitable_line"],
                            "codigoBarras": arts["barcode"],
                        },
                    },
                },
                digitable_line=arts["digitable_line"],
                barcode=arts["barcode"],
                payment_url=arts["payment_url"],
                boleto_pdf_url=arts["boleto_pdf_url"],
                extras={"situacao": "A_RECEBER"},
            )
        path = f"{self._charge_path().rstrip('/')}/{ref}"
        data = self._request("GET", path)
        payload = data if isinstance(data, dict) else {}
        arts = inter_artifacts(payload)
        hub_status = map_inter_situacao(arts.get("situacao")) or "registered"
        return ChargeRegisterResult(
            external_ref=str(arts.get("codigo_solicitacao") or ref),
            status=hub_status,
            raw={"provider": self.kind, "mode": "http", **payload},
            digitable_line=str(arts.get("digitable_line") or ""),
            barcode=str(arts.get("barcode") or ""),
            pix_copy_paste=str(arts.get("pix_copy_paste") or ""),
            extras=arts,
        )

    def baixar_pdf(self, *, ref: str) -> bytes:
        """GET .../{codigo}/pdf — binário. Stub devolve PDF mínimo válido."""
        if self.mode != "http":
            return (
                b"%PDF-1.4\n"
                b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
                b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
                b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] >>endobj\n"
                b"xref\n0 4\n0000000000 65535 f \n"
                b"trailer<< /Size 4 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
            )
        path = f"{self._charge_path().rstrip('/')}/{ref}/pdf"
        return self._request_bytes("GET", path)

    def _webhook_path(self) -> str:
        if self.kind == "inter":
            return (
                getattr(settings, "INTER_WEBHOOK_PATH", None)
                or "/cobranca/v3/cobrancas/webhook"
            )
        raise PaymentGatewayError(
            f"Webhook Cobrança não suportado para provedor {self.kind}"
        )

    def registrar_webhook(self, *, webhook_url: str) -> dict[str, Any]:
        """PUT .../webhook — cadastro da URL de callback (estudo Inter §9.1)."""
        url = (webhook_url or "").strip()
        if not url:
            raise PaymentGatewayError("webhookUrl obrigatória")
        if self.mode != "http":
            return {
                "provider": self.kind,
                "mode": "stub",
                "action": "registrar_webhook",
                "webhookUrl": url,
            }
        return self._request(
            "PUT", self._webhook_path(), json={"webhookUrl": url}
        )

    def consultar_webhook(self) -> dict[str, Any]:
        if self.mode != "http":
            return {
                "provider": self.kind,
                "mode": "stub",
                "action": "consultar_webhook",
                "webhookUrl": getattr(settings, "INTER_WEBHOOK_PUBLIC_URL", "") or "",
            }
        return self._request("GET", self._webhook_path())

    def remover_webhook(self) -> dict[str, Any]:
        if self.mode != "http":
            return {
                "provider": self.kind,
                "mode": "stub",
                "action": "remover_webhook",
            }
        return self._request("DELETE", self._webhook_path())

    def retry_webhook_callbacks(
        self, *, codigo_solicitacao: list[str]
    ) -> dict[str, Any]:
        """POST .../webhook/callbacks/retry — até INTER_WEBHOOK_RETRY_MAX códigos."""
        refs = [str(x).strip() for x in (codigo_solicitacao or []) if str(x).strip()]
        if not refs:
            raise PaymentGatewayError("Informe ao menos um codigoSolicitacao")
        max_n = int(getattr(settings, "INTER_WEBHOOK_RETRY_MAX", 50) or 50)
        if len(refs) > max_n:
            raise PaymentGatewayError(
                f"Máximo de {max_n} codigoSolicitacao por retry"
            )
        if self.mode != "http":
            return {
                "provider": self.kind,
                "mode": "stub",
                "action": "retry_webhook_callbacks",
                "codigoSolicitacao": refs,
            }
        path = f"{self._webhook_path().rstrip('/')}/callbacks/retry"
        return self._request(
            "POST", path, json={"codigoSolicitacao": refs}
        )

    def _charge_path(self) -> str:
        key = f"{self.kind.upper()}_CHARGE_PATH"
        defaults = {
            "inter": "/cobranca/v3/cobrancas",
            "c6": "/v1/bank_slips",
        }
        return getattr(settings, key, None) or defaults.get(self.kind, "/cobrancas")

    def _cancel_spec(
        self, ref: str, *, motivo_cancelamento: str | None = None
    ) -> tuple[str, str, dict[str, Any] | None]:
        if self.kind == "c6":
            tmpl = getattr(settings, "C6_CANCEL_PATH_TMPL", None) or "/v1/bank_slips/{ref}/cancel"
            return "PUT", tmpl.format(ref=ref), None
        tmpl = (
            getattr(settings, "INTER_CANCEL_PATH_TMPL", None)
            or "/cobranca/v3/cobrancas/{ref}/cancelar"
        )
        motivo = (motivo_cancelamento or "").strip().upper()
        if not motivo:
            motivo = (
                getattr(settings, "INTER_CANCEL_MOTIVO", None) or DEFAULT_INTER_CANCEL_MOTIVO
            )
        motivo = str(motivo).strip().upper()
        if motivo not in INTER_CANCEL_MOTIVOS:
            raise PaymentGatewayError(
                f"motivoCancelamento inválido: {motivo}. "
                f"Use: {', '.join(sorted(INTER_CANCEL_MOTIVOS))}"
            )
        return "POST", tmpl.format(ref=ref), {"motivoCancelamento": motivo}

    def _charge_body(
        self,
        *,
        amount_cents: int,
        due_date: date,
        description: str,
        customer_document: str,
        customer_name: str,
        external_reference: str,
        customer_address: dict[str, Any] | None = None,
        customer_email: str = "",
        charge_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.kind == "c6":
            return self._c6_charge_body(
                amount_cents=amount_cents,
                due_date=due_date,
                description=description,
                customer_document=customer_document,
                customer_name=customer_name,
                external_reference=external_reference,
                customer_address=customer_address,
            )
        return self._inter_charge_body(
            amount_cents=amount_cents,
            due_date=due_date,
            description=description,
            customer_document=customer_document,
            customer_name=customer_name,
            external_reference=external_reference,
            customer_address=customer_address,
            customer_email=customer_email,
            charge_options=charge_options,
        )

    def _inter_charge_body(
        self,
        *,
        amount_cents: int,
        due_date: date,
        description: str,
        customer_document: str,
        customer_name: str,
        external_reference: str,
        customer_address: dict[str, Any] | None = None,
        customer_email: str = "",
        charge_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Contrato: developers.inter.co Cobrança v3 (BolePix)
        opts = charge_options or {}
        addr = customer_address or {}
        pagador: dict[str, Any] = {
            "cpfCnpj": _digits(customer_document),
            "nome": customer_name[:100],
            "tipoPessoa": _tipo_pessoa(customer_document),
            "endereco": (
                addr.get("logradouro") or addr.get("endereco") or "NAO INFORMADO"
            )[:90],
            "numero": str(addr.get("numero") or "S/N")[:10],
            "bairro": (addr.get("bairro") or "CENTRO")[:60],
            "cidade": _inter_cidade(addr),
            "uf": (addr.get("uf") or "SP")[:2].upper(),
            "cep": _digits(str(addr.get("cep") or "01000000"))[:8],
        }
        email = (customer_email or addr.get("email") or "").strip()
        if email:
            pagador["email"] = email[:100]

        seu_numero = str(opts.get("seu_numero") or external_reference)[:15]
        if "num_dias_agenda" in opts and opts["num_dias_agenda"] is not None:
            num_dias = int(opts["num_dias_agenda"])
        else:
            num_dias = int(getattr(settings, "INTER_NUM_DIAS_AGENDA", 0) or 0)
        num_dias = max(0, min(60, num_dias))

        mensagem = _inter_mensagem(
            description=description,
            message_lines=opts.get("message_lines"),
        )
        body: dict[str, Any] = {
            "seuNumero": seu_numero,
            "valorNominal": round(amount_cents / 100, 2),
            "dataVencimento": due_date.isoformat(),
            "numDiasAgenda": num_dias,
            "pagador": pagador,
            "mensagem": mensagem,
        }
        multa = _inter_multa(opts.get("multa_percent"))
        if multa:
            body["multa"] = multa
        mora = _inter_mora(opts.get("mora_percent_am"))
        if mora:
            body["mora"] = mora
        return body

    def _c6_charge_body(
        self,
        *,
        amount_cents: int,
        due_date: date,
        description: str,
        customer_document: str,
        customer_name: str,
        external_reference: str,
        customer_address: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Contrato BaaS C6: POST /v1/bank_slips (snake_case)
        instr = (description or "Cobranca EXEQ Hub")[:80]
        addr = customer_address or {}
        return {
            "external_reference_id": external_reference[:64],
            "amount": round(amount_cents / 100, 2),
            "due_date": due_date.isoformat(),
            "instructions": [instr],
            "billing_scheme": str(
                getattr(settings, "C6_BILLING_SCHEME", None) or "21"
            ),
            "our_number": _digits(external_reference)[:15] or external_reference[:15],
            "payer": {
                "name": customer_name[:100],
                "tax_id": _digits(customer_document),
                "address": {
                    "street": (
                        addr.get("logradouro")
                        or getattr(settings, "C6_PAYER_STREET", None)
                        or "NAO INFORMADO"
                    ),
                    "number": str(
                        addr.get("numero")
                        or getattr(settings, "C6_PAYER_NUMBER", None)
                        or "S/N"
                    ),
                    "city": _inter_cidade(addr)
                    if addr
                    else (getattr(settings, "C6_PAYER_CITY", None) or "SAO PAULO"),
                    "state": (
                        addr.get("uf")
                        or getattr(settings, "C6_PAYER_STATE", None)
                        or "SP"
                    ),
                    "zip_code": _digits(
                        str(
                            addr.get("cep")
                            or getattr(settings, "C6_PAYER_ZIP", None)
                            or "01000000"
                        )
                    ),
                },
            },
        }

    def _extract_ref(self, data: dict[str, Any]) -> str:
        if self.kind == "c6":
            return str(data.get("id") or data.get("bank_slip_id") or "")
        return str(
            data.get("codigoSolicitacao")
            or data.get("id")
            or data.get("nossoNumero")
            or ""
        )

    def _extra_headers(self, *, idempotency_key: str) -> dict[str, str]:
        headers: dict[str, str] = {"x-idempotency-key": idempotency_key}
        if self.kind == "inter":
            conta = getattr(settings, "INTER_CONTA_CORRENTE", "") or ""
            if conta:
                headers["x-conta-corrente"] = conta
        return headers

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.token:
            raise PaymentGatewayError(f"Token {self.kind} não configurado")
        if not self.base_url:
            raise PaymentGatewayError(f"Base URL {self.kind} não configurada")
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            **(kwargs.pop("headers", None) or {}),
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, headers=headers, **kwargs)
        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text} if response.text else {}
        if response.status_code >= 400:
            raise PaymentGatewayError(f"{self.kind} HTTP {response.status_code}: {data}")
        return data if isinstance(data, dict) else {"data": data}

    def _request_bytes(self, method: str, path: str, **kwargs) -> bytes:
        if not self.token:
            raise PaymentGatewayError(f"Token {self.kind} não configurado")
        if not self.base_url:
            raise PaymentGatewayError(f"Base URL {self.kind} não configurada")
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/pdf",
            **(kwargs.pop("headers", None) or {}),
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise PaymentGatewayError(
                f"{self.kind} HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.content


def _inter_mensagem(
    *, description: str, message_lines: list[str] | None
) -> dict[str, str]:
    if message_lines:
        lines = list(message_lines[:5])
        while len(lines) < 5:
            lines.append("")
        return {
            f"linha{i}": str(lines[i - 1] or "")[:78]
            for i in range(1, 6)
        }
    text = (description or "Cobranca EXEQ Hub")[:78]
    return {"linha1": text, "linha2": "", "linha3": "", "linha4": "", "linha5": ""}


def _inter_multa(percent: float | int | None) -> dict[str, Any] | None:
    if percent is None:
        return None
    taxa = float(percent)
    if taxa <= 0:
        return {"codigo": "NAOTEMMULTA", "taxa": 0, "valor": 0}
    return {"codigo": "PERCENTUAL", "taxa": taxa, "valor": 0}


def _inter_mora(percent_am: float | int | None) -> dict[str, Any] | None:
    if percent_am is None:
        return None
    taxa = float(percent_am)
    if taxa <= 0:
        return {"codigo": "ISENTO", "taxa": 0, "valor": 0}
    return {"codigo": "TAXAMENSAL", "taxa": taxa, "valor": 0}


class InterPaymentGateway(BankPaymentGateway):
    """Inter Cobrança v3 — HTTP com InterAuthClient (mTLS+OAuth) ou Bearer legado."""

    def __init__(
        self,
        *,
        token: str | None = None,
        mode: str | None = None,
        auth: InterAuthClient | None = None,
    ):
        self.auth = auth
        super().__init__(
            kind="inter",
            token=token,
            base_url=getattr(settings, "INTER_API_BASE_URL", "") or "",
            mode=mode,
        )

    def _extra_headers(self, *, idempotency_key: str) -> dict[str, str]:
        headers = super()._extra_headers(idempotency_key=idempotency_key)
        if self.auth and self.auth.credentials.conta_corrente:
            headers["x-conta-corrente"] = self.auth.credentials.conta_corrente
        return headers

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if self.auth is not None:
            return self.auth.request_json(
                method,
                path,
                headers=kwargs.pop("headers", None),
                **kwargs,
            )
        return super()._request(method, path, **kwargs)

    def _request_bytes(self, method: str, path: str, **kwargs) -> bytes:
        if self.auth is not None:
            return self.auth.request_bytes(
                method,
                path,
                headers=kwargs.pop("headers", None),
                **kwargs,
            )
        return super()._request_bytes(method, path, **kwargs)


class C6PaymentGateway(BankPaymentGateway):
    def __init__(self, *, token: str | None = None, mode: str | None = None):
        super().__init__(
            kind="c6",
            token=token,
            base_url=getattr(settings, "C6_API_BASE_URL", "") or "",
            mode=mode,
        )


# Compat: nome antigo usado em imports/testes
StubBankPaymentGateway = BankPaymentGateway
