import httpx

from app.config import Settings
from app.services.sharepoint_service import SharePointService


def configured_settings() -> Settings:
    return Settings(
        microsoft_tenant_id="tenant-id",
        microsoft_client_id="client-id",
        microsoft_client_secret="client-secret",
        sharepoint_drive_id="drive-id",
        sharepoint_folder_id="folder-id",
    )


def test_sharepoint_matches_exact_filename_stems_and_ignores_folders() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(
            200,
            json={
                "value": [
                    {"name": "AB-100.xlsx", "webUrl": "https://example.com/ab", "file": {}},
                    {"name": "AB-100-1.xlsx", "webUrl": "https://example.com/ab-1", "file": {}},
                    {"name": "AB-200.xlsm", "webUrl": "https://example.com/ab-200", "file": {}},
                    {"name": "folder", "webUrl": "https://example.com/folder", "folder": {}},
                ]
            },
        )

    service = SharePointService(
        configured_settings(), transport=httpx.MockTransport(handler)
    )
    result = service.search_many(("AB-100", "AB-200", "AB-300"))

    assert result["AB-100"].status == "found"
    assert result["AB-100"].url == "https://example.com/ab"
    assert result["AB-200"].status == "found"
    assert result["AB-300"].status == "not_found"


def test_sharepoint_reports_permission_errors_for_all_requested_parts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(403, json={"error": {"code": "accessDenied"}})

    service = SharePointService(
        configured_settings(), transport=httpx.MockTransport(handler)
    )

    result = service.search_many(("AB-100", "AB-200"))

    assert {item.status for item in result.values()} == {"permission_error"}
