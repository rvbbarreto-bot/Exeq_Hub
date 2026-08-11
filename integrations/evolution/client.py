from __future__ import annotations

import base64
from typing import Protocol

import httpx
from django.conf import settings

PROVIDER = "evolution"


class EvolutionGateway(Protocol):
    def send_text(self, *, phone_e164: str, text: str) -> dict: ...

    def send_media(
        self,
        *,
        phone_e164: str,
        filename: str,
        mime_type: str,
        data: bytes,
        caption: str = "",
    ) -> dict: ...


class EvolutionStubGateway:
    def send_text(self, *, phone_e164: str, text: str) -> dict:
        return {
            "ok": True,
            "ref": f"evo-{phone_e164[-4:]}",
            "mode": "stub",
            "provider": PROVIDER,
        }

    def send_media(
        self,
        *,
        phone_e164: str,
        filename: str,
        mime_type: str,
        data: bytes,
        caption: str = "",
    ) -> dict:
        return {
            "ok": True,
            "ref": f"evo-media-{phone_e164[-4:]}",
            "mode": "stub",
            "provider": PROVIDER,
            "filename": filename,
            "bytes": len(data),
        }


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

    def _not_configured(self) -> dict:
        return {
            "ok": False,
            "error": "Evolution não configurada",
            "mode": "http",
            "provider": PROVIDER,
        }

    def _parse_ref(self, data) -> str:
        if isinstance(data, dict):
            return str(data.get("key", {}).get("id") or data.get("id") or "")
        return ""

    def send_text(self, *, phone_e164: str, text: str) -> dict:
        if not self.base_url or not self.api_key or not self.instance:
            return self._not_configured()
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
        return {
            "ok": response.status_code < 400,
            "ref": self._parse_ref(data),
            "mode": "http",
            "provider": PROVIDER,
            "raw": data,
            "status_code": response.status_code,
        }

    def send_media(
        self,
        *,
        phone_e164: str,
        filename: str,
        mime_type: str,
        data: bytes,
        caption: str = "",
    ) -> dict:
        if not self.base_url or not self.api_key or not self.instance:
            return self._not_configured()
        number = phone_e164.lstrip("+")
        url = f"{self.base_url}/message/sendMedia/{self.instance}"
        b64 = base64.b64encode(data).decode("ascii")
        media = f"data:{mime_type};base64,{b64}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                url,
                headers={"apikey": self.api_key, "Content-Type": "application/json"},
                json={
                    "number": number,
                    "mediatype": "document",
                    "mimetype": mime_type,
                    "media": media,
                    "fileName": filename,
                    "caption": caption or filename,
                },
            )
        try:
            body = response.json()
        except Exception:
            body = {"raw_text": response.text}
        return {
            "ok": response.status_code < 400,
            "ref": self._parse_ref(body),
            "mode": "http",
            "provider": PROVIDER,
            "raw": body,
            "status_code": response.status_code,
            "filename": filename,
        }


def get_evolution_gateway() -> EvolutionGateway:
    mode = (settings.EVOLUTION_HTTP_MODE or "stub").lower()
    if mode == "http":
        return EvolutionHttpGateway()
    return EvolutionStubGateway()
