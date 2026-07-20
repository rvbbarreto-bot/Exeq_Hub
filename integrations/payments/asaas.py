from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import httpx
from django.conf import settings

from integrations.payments.errors import PaymentGatewayError
from integrations.payments.port import ChargeRegisterResult


class AsaasPaymentGateway:
    """Adaptador Asaas — stub (default) ou HTTP."""

    kind = "asaas"

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        mode: str | None = None,
        timeout: float = 30.0,
    ):
        self.token = token if token is not None else (settings.ASAAS_API_TOKEN or "")
        self.base_url = (
            base_url
            or settings.ASAAS_API_BASE_URL
            or "https://sandbox.asaas.com/api/v3"
        ).rstrip("/")
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
            ref = f"asaas_{uuid4().hex[:16]}"
            return ChargeRegisterResult(
                external_ref=ref,
                status="registered",
                raw={
                    "provider": self.kind,
                    "mode": "stub",
                    "action": "registrar",
                    "externalReference": external_reference,
                    "idempotency_key": idempotency_key,
                },
            )

        customer_id = self._ensure_customer(
            document=customer_document,
            name=customer_name,
        )
        value = round(amount_cents / 100, 2)
        data = self._request(
            "POST",
            "/payments",
            json={
                "customer": customer_id,
                "billingType": "UNDEFINED",
                "value": value,
                "dueDate": due_date.isoformat(),
                "description": description or "Cobrança EXEQ Hub",
                "externalReference": external_reference,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        ref = str(data.get("id") or "")
        if not ref:
            raise PaymentGatewayError(f"Asaas sem id na resposta: {data}")
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
        data = self._request("DELETE", f"/payments/{ref}")
        return ChargeRegisterResult(
            external_ref=ref,
            status="cancelled",
            raw={"provider": self.kind, "mode": "http", **(data if isinstance(data, dict) else {})},
        )

    def _ensure_customer(self, *, document: str, name: str) -> str:
        digits = "".join(ch for ch in document if ch.isdigit())
        found = self._request("GET", "/customers", params={"cpfCnpj": digits})
        data = found.get("data") if isinstance(found, dict) else None
        if isinstance(data, list) and data:
            return str(data[0]["id"])
        created = self._request(
            "POST",
            "/customers",
            json={"name": name, "cpfCnpj": digits},
        )
        cid = str(created.get("id") or "")
        if not cid:
            raise PaymentGatewayError(f"Asaas customer sem id: {created}")
        return cid

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.token:
            raise PaymentGatewayError("ASAAS_API_TOKEN não configurado")
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        headers = {
            "Content-Type": "application/json",
            "access_token": self.token,
            **headers,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, headers=headers, **kwargs)
        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text}
        if response.status_code >= 400:
            raise PaymentGatewayError(f"Asaas HTTP {response.status_code}: {data}")
        return data if isinstance(data, dict) else {"data": data}
