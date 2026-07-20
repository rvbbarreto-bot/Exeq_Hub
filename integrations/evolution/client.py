from __future__ import annotations

from typing import Protocol

import httpx
from django.conf import settings


class EvolutionGateway(Protocol):
    def send_text(self, *, phone_e164: str, text: str) -> dict: ...


class EvolutionStubGateway:
    def send_text(self, *, phone_e164: str, text: str) -> dict:
        return {"ok": True, "ref": f"evo-{phone_e164[-4:]}", "mode": "stub"}


class EvolutionHttpGateway:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        instance: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (
            base_url or settings.EVOLUTION_API_BASE_URL or ""
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else (settings.EVOLUTION_API_KEY or "")
        self.instance = instance or settings.EVOLUTION_INSTANCE or ""
        self.timeout = timeout

    def send_text(self, *, phone_e164: str, text: str) -> dict:
        if not self.base_url or not self.api_key or not self.instance:
            return {"ok": False, "error": "Evolution não configurada", "mode": "http"}
        number = phone_e164.lstrip("+")
        url = f"{self.base_url}/message/sendText/{self.instance}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                url,
                headers={"apikey": self.api_key, "Content-Type": "application/json"},
                json={"number": number, "text": text},
            )
        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text}
        ok = response.status_code < 400
        ref = ""
        if isinstance(data, dict):
            ref = str(data.get("key", {}).get("id") or data.get("id") or "")
        return {"ok": ok, "ref": ref, "mode": "http", "raw": data, "status_code": response.status_code}


def get_evolution_gateway() -> EvolutionGateway:
    mode = (settings.EVOLUTION_HTTP_MODE or "stub").lower()
    if mode == "http":
        return EvolutionHttpGateway()
    return EvolutionStubGateway()
