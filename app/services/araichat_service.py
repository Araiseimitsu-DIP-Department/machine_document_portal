from __future__ import annotations

import httpx

from app.config import Settings


class AraichatError(RuntimeError):
    """ARAICHAT rejected a request or is not configured."""


class AraichatAmbiguousError(AraichatError):
    """The request may have reached ARAICHAT; automatic resend is unsafe."""


class AraichatService:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = settings.araichat_base_url
        self.api_key = settings.araichat_api_key
        self.room_id = settings.araichat_room_id
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.room_id)

    def send_text(self, message: str, *, idempotency_key: str) -> None:
        if not self.configured:
            raise AraichatError("ARAICHAT settings are incomplete")
        url = (
            f"{(self.base_url or '').rstrip('/')}/api/integrations/send/"
            f"{self.room_id}"
        )
        try:
            with httpx.Client(timeout=(10.0, 60.0), transport=self.transport) as client:
                response = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Idempotency-Key": idempotency_key,
                    },
                    data={"text": message},
                )
        except httpx.RequestError as exc:
            raise AraichatAmbiguousError(
                "ARAICHAT send result is unknown; automatic resend was stopped"
            ) from exc
        if response.is_error:
            raise AraichatError(
                f"ARAICHAT request failed with HTTP {response.status_code}"
            )
