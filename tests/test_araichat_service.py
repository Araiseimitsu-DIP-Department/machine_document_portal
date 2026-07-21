import httpx

from app.config import Settings
from app.services.araichat_service import AraichatService


def test_araichat_sends_text_with_room_and_idempotency_key() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["idempotency_key"] = request.headers.get("Idempotency-Key")
        captured["content"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    service = AraichatService(
        Settings(
            araichat_base_url="https://chat.example.com/",
            araichat_api_key="secret-key",
            araichat_room_id="24",
        ),
        transport=httpx.MockTransport(handler),
    )

    service.send_text("通知本文", idempotency_key="next-day:2026-07-27")

    assert captured["url"] == "https://chat.example.com/api/integrations/send/24"
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["idempotency_key"] == "next-day:2026-07-27"
    assert "%E9%80%9A%E7%9F%A5%E6%9C%AC%E6%96%87" in str(captured["content"])
