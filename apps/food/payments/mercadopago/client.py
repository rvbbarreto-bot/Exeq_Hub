"""Cliente HTTP Mercado Pago Payments API (Food)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from django.conf import settings

from apps.accounts.secrets import get_tenant_secret_plaintext
from apps.food.exceptions import FoodPaymentProviderError


@dataclass(frozen=True)
class MercadoPagoPaymentResult:
    payment_id: str
    status: str
    pix_copy_paste: str = ""
    status_detail: str = ""
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class MercadoPagoPixPaymentResult:
    payment_id: str
    status: str
    pix_copy_paste: str
    raw: dict[str, Any]


def resolve_mp_http_mode() -> str:
    return (
        getattr(settings, "FOOD_MP_HTTP_MODE", None)
        or getattr(settings, "PAYMENT_HTTP_MODE", "stub")
        or "stub"
    ).lower()


def get_public_key(*, tenant) -> str:
    key = get_tenant_secret_plaintext(
        tenant=tenant,
        provider="mercadopago",
        key_name="public_key",
    )
    if not key:
        key = getattr(settings, "MERCADOPAGO_PUBLIC_KEY", "") or ""
    return (key or "").strip()


def _sanitize_gateway_payload(data: dict[str, Any]) -> dict[str, Any]:
    clean = dict(data)
    clean.pop("token", None)
    return clean


def _map_payment_result(data: dict[str, Any]) -> MercadoPagoPaymentResult:
    payment_id = str(data.get("id") or "")
    if not payment_id:
        raise FoodPaymentProviderError("Mercado Pago não retornou payment id.")
    return MercadoPagoPaymentResult(
        payment_id=payment_id,
        status=str(data.get("status") or "pending"),
        pix_copy_paste=_extract_pix_copy_paste(data),
        status_detail=str(data.get("status_detail") or ""),
        raw=_sanitize_gateway_payload(data),
    )


def get_access_token(*, tenant) -> str:
    token = get_tenant_secret_plaintext(
        tenant=tenant,
        provider="mercadopago",
        key_name="access_token",
    )
    if not token:
        token = getattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "") or ""
    return (token or "").strip()


def _extract_pix_copy_paste(data: dict[str, Any]) -> str:
    poi = data.get("point_of_interaction") or {}
    if not isinstance(poi, dict):
        return ""
    tx = poi.get("transaction_data") or {}
    if not isinstance(tx, dict):
        return ""
    return str(tx.get("qr_code") or tx.get("qr_code_base64") or "").strip()


class MercadoPagoClient:
    def __init__(
        self,
        *,
        tenant,
        access_token: str | None = None,
        mode: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.tenant = tenant
        self.mode = (mode or resolve_mp_http_mode()).lower()
        self.access_token = (access_token or get_access_token(tenant=tenant)).strip()
        self.base_url = (base_url or "https://api.mercadopago.com").rstrip("/")
        self.timeout = timeout

    def create_pix_payment(
        self,
        *,
        amount_cents: int,
        description: str,
        external_reference: str,
        idempotency_key: str,
        payer: dict[str, Any],
    ) -> MercadoPagoPixPaymentResult:
        if self.mode != "http":
            return self._stub_pix(
                amount_cents=amount_cents,
                external_reference=external_reference,
                idempotency_key=idempotency_key,
            )
        if not self.access_token:
            raise FoodPaymentProviderError(
                "Credencial Mercado Pago (access_token) não configurada para o tenant."
            )
        body = {
            "transaction_amount": round(amount_cents / 100, 2),
            "description": (description or "Pedido Food")[:256],
            "payment_method_id": "pix",
            "external_reference": external_reference[:256],
            "payer": payer,
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key[:64],
        }
        url = f"{self.base_url}/v1/payments"
        try:
            response = httpx.post(
                url,
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise FoodPaymentProviderError(
                f"Falha de rede ao criar pagamento Mercado Pago: {exc}"
            ) from exc
        if response.status_code >= 400:
            detail = response.text[:500]
            raise FoodPaymentProviderError(
                f"Mercado Pago recusou pagamento Pix (HTTP {response.status_code}): {detail}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise FoodPaymentProviderError(
                "Resposta inválida do Mercado Pago ao criar Pix."
            ) from exc
        if not isinstance(data, dict):
            raise FoodPaymentProviderError("Resposta Mercado Pago em formato inesperado.")
        mapped = _map_payment_result(data)
        if not mapped.pix_copy_paste:
            raise FoodPaymentProviderError(
                "Mercado Pago não retornou PIX copia e cola (qr_code)."
            )
        return MercadoPagoPixPaymentResult(
            payment_id=mapped.payment_id,
            status=mapped.status,
            pix_copy_paste=mapped.pix_copy_paste,
            raw=mapped.raw or data,
        )

    def create_card_payment(
        self,
        *,
        amount_cents: int,
        description: str,
        external_reference: str,
        idempotency_key: str,
        payer: dict[str, Any],
        token: str,
        payment_method_id: str,
        issuer_id: str = "",
        installments: int = 1,
    ) -> MercadoPagoPaymentResult:
        token = (token or "").strip()
        payment_method_id = (payment_method_id or "").strip().lower()
        if not token:
            raise FoodPaymentProviderError("Token de cartão ausente.")
        if not payment_method_id:
            raise FoodPaymentProviderError("payment_method_id ausente.")
        installments = max(1, int(installments or 1))

        if self.mode != "http":
            return self._stub_card(
                amount_cents=amount_cents,
                external_reference=external_reference,
                idempotency_key=idempotency_key,
                payment_method_id=payment_method_id,
            )

        if not self.access_token:
            raise FoodPaymentProviderError(
                "Credencial Mercado Pago (access_token) não configurada para o tenant."
            )
        body: dict[str, Any] = {
            "transaction_amount": round(amount_cents / 100, 2),
            "token": token,
            "description": (description or "Pedido Food")[:256],
            "installments": installments,
            "payment_method_id": payment_method_id,
            "external_reference": external_reference[:256],
            "payer": payer,
        }
        if issuer_id:
            body["issuer_id"] = str(issuer_id)
        data = self._post_payment(body=body, idempotency_key=idempotency_key)
        return _map_payment_result(data)

    def _post_payment(self, *, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key[:64],
        }
        url = f"{self.base_url}/v1/payments"
        try:
            response = httpx.post(
                url,
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise FoodPaymentProviderError(
                f"Falha de rede ao criar pagamento Mercado Pago: {exc}"
            ) from exc
        if response.status_code >= 400:
            detail = response.text[:500]
            raise FoodPaymentProviderError(
                f"Mercado Pago recusou pagamento (HTTP {response.status_code}): {detail}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise FoodPaymentProviderError(
                "Resposta inválida do Mercado Pago."
            ) from exc
        if not isinstance(data, dict):
            raise FoodPaymentProviderError("Resposta Mercado Pago em formato inesperado.")
        return data

    def _stub_card(
        self,
        *,
        amount_cents: int,
        external_reference: str,
        idempotency_key: str,
        payment_method_id: str,
    ) -> MercadoPagoPaymentResult:
        payment_id = f"mp_card_{uuid4().hex[:12]}"
        raw = {
            "id": payment_id,
            "status": "approved",
            "status_detail": "accredited",
            "payment_method_id": payment_method_id,
            "external_reference": external_reference,
            "idempotency_key": idempotency_key,
            "transaction_amount": round(amount_cents / 100, 2),
            "mode": "stub",
        }
        return MercadoPagoPaymentResult(
            payment_id=payment_id,
            status="approved",
            status_detail="accredited",
            raw=raw,
        )

    def _stub_pix(
        self,
        *,
        amount_cents: int,
        external_reference: str,
        idempotency_key: str,
    ) -> MercadoPagoPixPaymentResult:
        payment_id = f"mp_stub_{uuid4().hex[:12]}"
        pix = (
            f"00020126580014BR.GOV.BCB.PIX0136{payment_id}520400005303986"
            f"540{amount_cents / 100:.2f}5802BR5925EXEQ FOOD STUB6009SAO PAULO"
            f"62070503***6304ABCD"
        )
        raw = {
            "id": payment_id,
            "status": "pending",
            "external_reference": external_reference,
            "idempotency_key": idempotency_key,
            "mode": "stub",
            "point_of_interaction": {
                "transaction_data": {"qr_code": pix},
            },
        }
        return MercadoPagoPixPaymentResult(
            payment_id=payment_id,
            status="pending",
            pix_copy_paste=pix,
            raw=raw,
        )

    def get_payment(self, *, payment_id: str) -> dict[str, Any]:
        if self.mode != "http":
            return self.stub_payment_detail(payment_id=payment_id, status="approved")
        if not self.access_token:
            raise FoodPaymentProviderError(
                "Credencial Mercado Pago não configurada para consulta."
            )
        url = f"{self.base_url}/v1/payments/{payment_id}"
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise FoodPaymentProviderError(
                f"Falha de rede ao consultar pagamento Mercado Pago: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise FoodPaymentProviderError(
                f"Mercado Pago recusou consulta (HTTP {response.status_code})."
            )
        data = response.json()
        if not isinstance(data, dict):
            raise FoodPaymentProviderError("Resposta Mercado Pago inválida.")
        return data

    def stub_payment_detail(
        self,
        *,
        payment_id: str,
        status: str = "approved",
        amount_cents: int | None = None,
    ) -> dict[str, Any]:
        amount = (amount_cents or 100) / 100
        return {
            "id": payment_id,
            "status": status,
            "status_detail": "accredited" if status == "approved" else status,
            "transaction_amount": amount,
            "mode": "stub",
        }
