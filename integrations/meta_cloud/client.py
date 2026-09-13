"""WhatsApp Cloud API oficial (Meta Graph API) — paridade de contrato com Evolution."""

from __future__ import annotations

import httpx
from django.conf import settings

PROVIDER = "meta"


class MetaCloudStubGateway:
    def send_text(self, *, phone_e164: str, text: str) -> dict:
        return {
            "ok": True,
            "ref": f"wamid-stub-{phone_e164[-4:]}",
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
            "ref": f"wamid-media-stub-{phone_e164[-4:]}",
            "mode": "stub",
            "provider": PROVIDER,
            "filename": filename,
            "bytes": len(data),
        }


class MetaCloudHttpGateway:
    def __init__(
        self,
        *,
        token: str | None = None,
        phone_number_id: str | None = None,
        graph_version: str | None = None,
        timeout: float = 30.0,
    ):
        self.token = token if token is not None else (settings.META_WHATSAPP_TOKEN or "")
        self.phone_number_id = (
            phone_number_id or settings.META_WHATSAPP_PHONE_NUMBER_ID or ""
        )
        self.graph_version = graph_version or settings.META_GRAPH_API_VERSION or "v23.0"
        self.timeout = timeout

    def _not_configured(self) -> dict:
        return {
            "ok": False,
            "error": "Meta Cloud API não configurada",
            "mode": "http",
            "provider": PROVIDER,
        }

    def _messages_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.graph_version}"
            f"/{self.phone_number_id}/messages"
        )

    def _media_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.graph_version}"
            f"/{self.phone_number_id}/media"
        )

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _parse_message_ref(self, data) -> str:
        if isinstance(data, dict):
            messages = data.get("messages") or []
            if messages and isinstance(messages[0], dict):
                return str(messages[0].get("id") or "")
        return ""

    def send_text(self, *, phone_e164: str, text: str) -> dict:
        if not self.token or not self.phone_number_id:
            return self._not_configured()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self._messages_url(),
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone_e164.lstrip("+"),
                    "type": "text",
                    "text": {"body": text},
                },
            )
        try:
            data = response.json()
        except Exception:
            data = {"raw_text": response.text}
        return {
            "ok": response.status_code < 400,
            "ref": self._parse_message_ref(data),
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
        """Upload do arquivo + envio como document (contrato Cloud API)."""
        if not self.token or not self.phone_number_id:
            return self._not_configured()
        with httpx.Client(timeout=self.timeout) as client:
            upload = client.post(
                self._media_url(),
                headers=self._auth_headers(),
                data={"messaging_product": "whatsapp", "type": mime_type},
                files={"file": (filename, data, mime_type)},
            )
            try:
                upload_body = upload.json()
            except Exception:
                upload_body = {"raw_text": upload.text}
            if upload.status_code >= 400:
                return {
                    "ok": False,
                    "ref": "",
                    "mode": "http",
                    "provider": PROVIDER,
                    "raw": upload_body,
                    "status_code": upload.status_code,
                    "filename": filename,
                    "error": "Falha no upload de mídia Meta",
                }
            media_id = str(upload_body.get("id") or "")
            if not media_id:
                return {
                    "ok": False,
                    "ref": "",
                    "mode": "http",
                    "provider": PROVIDER,
                    "raw": upload_body,
                    "status_code": upload.status_code,
                    "filename": filename,
                    "error": "Meta não retornou media id",
                }
            response = client.post(
                self._messages_url(),
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": phone_e164.lstrip("+"),
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": filename,
                        "caption": caption or filename,
                    },
                },
            )
        try:
            body = response.json()
        except Exception:
            body = {"raw_text": response.text}
        return {
            "ok": response.status_code < 400,
            "ref": self._parse_message_ref(body),
            "mode": "http",
            "provider": PROVIDER,
            "raw": body,
            "status_code": response.status_code,
            "filename": filename,
            "media_id": media_id,
        }


def get_meta_cloud_gateway():
    mode = (settings.META_WHATSAPP_HTTP_MODE or "stub").lower()
    if mode == "http":
        return MetaCloudHttpGateway()
    return MetaCloudStubGateway()
