from dataclasses import dataclass
from typing import Protocol

import httpx


class WhatsAppProvider(Protocol):
    async def send_appointment_confirmation(
        self,
        *,
        recipient: str,
        customer_name: str,
        service: str,
        starts_at_text: str,
        idempotency_key: str,
    ) -> str: ...


@dataclass(frozen=True)
class WhatsAppTemplateConfig:
    messages_url: str
    access_token: str
    template_name: str
    language_code: str = "en"


class WhatsAppTemplateProvider:
    def __init__(
        self,
        config: WhatsAppTemplateConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    async def send_appointment_confirmation(
        self,
        *,
        recipient: str,
        customer_name: str,
        service: str,
        starts_at_text: str,
        idempotency_key: str,
    ) -> str:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": self._config.template_name,
                "language": {"code": self._config.language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": customer_name},
                            {"type": "text", "text": service},
                            {"type": "text", "text": starts_at_text},
                        ],
                    }
                ],
            },
        }
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
            "X-Vaani-Idempotency-Key": idempotency_key,
        }

        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=20.0,
        ) as client:
            response = await client.post(
                self._config.messages_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        messages = data.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise RuntimeError("WhatsApp response did not include a message id")
        return str(messages[0]["id"])
