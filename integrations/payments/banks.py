"""Gateway bancário enxuto — stub (default) ou HTTP (Inter Cobrança v3 / C6 bank_slips)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import httpx
from django.conf import settings

from integrations.payments.errors import PaymentGatewayError
from integrations.payments.port import ChargeRegisterResult


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _tipo_pessoa(document: str) -> str:
    return "JURIDICA" if len(_digits(document)) > 11 else "FISICA"


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
    ) -> ChargeRegisterResult:
        if self.mode != "http":
            ref = f"{self.kind}_{uuid4().hex[:16]}"
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
                },
            )

        body = self._charge_body(
            amount_cents=amount_cents,
            due_date=due_date,
            description=description,
            customer_document=customer_document,
            customer_name=customer_name,
            external_reference=external_reference,
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
        return ChargeRegisterResult(
            external_ref=ref,
            status="registered",
            raw={"provider": self.kind, "mode": "http", **data},
        )

    def cancelar(self, *, ref: str) -> ChargeRegisterResult:
        if self.mode != "http":
            return ChargeRegisterResult(
                external_ref=ref,
                status="cancelled",
                raw={
                    "provider": self.kind,
                    "mode": "stub",
                    "action": "cancelar",
                    "ref": ref,
                },
            )
        method, path, body = self._cancel_spec(ref)
        data = self._request(method, path, json=body) if body is not None else self._request(method, path)
        return ChargeRegisterResult(
            external_ref=ref,
            status="cancelled",
            raw={"provider": self.kind, "mode": "http", **(data if isinstance(data, dict) else {})},
        )

    def _charge_path(self) -> str:
        key = f"{self.kind.upper()}_CHARGE_PATH"
        defaults = {
            "inter": "/cobranca/v3/cobrancas",
            "c6": "/v1/bank_slips",
        }
        return getattr(settings, key, None) or defaults.get(self.kind, "/cobrancas")

    def _cancel_spec(self, ref: str) -> tuple[str, str, dict[str, Any] | None]:
        if self.kind == "c6":
            tmpl = getattr(settings, "C6_CANCEL_PATH_TMPL", None) or "/v1/bank_slips/{ref}/cancel"
            return "PUT", tmpl.format(ref=ref), None
        tmpl = (
            getattr(settings, "INTER_CANCEL_PATH_TMPL", None)
            or "/cobranca/v3/cobrancas/{ref}/cancelar"
        )
        motivo = getattr(settings, "INTER_CANCEL_MOTIVO", None) or "ACERTOS"
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
    ) -> dict[str, Any]:
        if self.kind == "c6":
            return self._c6_charge_body(
                amount_cents=amount_cents,
                due_date=due_date,
                description=description,
                customer_document=customer_document,
                customer_name=customer_name,
                external_reference=external_reference,
            )
        return self._inter_charge_body(
            amount_cents=amount_cents,
            due_date=due_date,
            description=description,
            customer_document=customer_document,
            customer_name=customer_name,
            external_reference=external_reference,
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
    ) -> dict[str, Any]:
        # Contrato: developers.inter.co Cobrança v3 (BolePix)
        return {
            "seuNumero": external_reference[:15],
            "valorNominal": round(amount_cents / 100, 2),
            "dataVencimento": due_date.isoformat(),
            "numDiasAgenda": int(getattr(settings, "INTER_NUM_DIAS_AGENDA", 0) or 0),
            "pagador": {
                "cpfCnpj": _digits(customer_document),
                "nome": customer_name[:100],
                "tipoPessoa": _tipo_pessoa(customer_document),
            },
            "mensagem": {"linha1": (description or "Cobranca EXEQ Hub")[:80]},
        }

    def _c6_charge_body(
        self,
        *,
        amount_cents: int,
        due_date: date,
        description: str,
        customer_document: str,
        customer_name: str,
        external_reference: str,
    ) -> dict[str, Any]:
        # Contrato BaaS C6: POST /v1/bank_slips (snake_case)
        instr = (description or "Cobranca EXEQ Hub")[:80]
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
                    "street": getattr(settings, "C6_PAYER_STREET", None) or "NAO INFORMADO",
                    "number": getattr(settings, "C6_PAYER_NUMBER", None) or "S/N",
                    "city": getattr(settings, "C6_PAYER_CITY", None) or "SAO PAULO",
                    "state": getattr(settings, "C6_PAYER_STATE", None) or "SP",
                    "zip_code": _digits(
                        getattr(settings, "C6_PAYER_ZIP", None) or "01000000"
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


class InterPaymentGateway(BankPaymentGateway):
    def __init__(self, *, token: str | None = None, mode: str | None = None):
        super().__init__(
            kind="inter",
            token=token,
            base_url=getattr(settings, "INTER_API_BASE_URL", "") or "",
            mode=mode,
        )


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
