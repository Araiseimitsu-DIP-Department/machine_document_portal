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


def test_sharepoint_matches_literal_filename_stems_and_ignores_folders() -> None:
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
                    {"name": "AB100.xlsx", "webUrl": "https://example.com/ab100", "file": {}},
                    {"name": "folder", "webUrl": "https://example.com/folder", "folder": {}},
                ]
            },
        )

    service = SharePointService(
        configured_settings(), transport=httpx.MockTransport(handler)
    )
    result = service.search_many(
        ("AB-100", "AB-200", "AB-300", "ab-100", "ＡＢ－１００", "AB 100")
    )

    assert result["AB-100"].status == "found"
    assert result["AB-100"].url == "https://example.com/ab"
    assert result["AB-200"].status == "found"
    assert result["AB-300"].status == "not_found"
    assert result["ab-100"].status == "not_found"
    assert result["ＡＢ－１００"].status == "not_found"
    assert result["AB 100"].status == "not_found"


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


def test_sharepoint_recursively_searches_nested_folders_and_detects_duplicates() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        path = request.url.path
        requested_paths.append(path)
        if path.endswith("/items/folder-id/children"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "sub-a", "name": "A", "folder": {}},
                        {"id": "sub-b", "name": "B", "folder": {}},
                    ]
                },
            )
        if path.endswith("/items/sub-a/children"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "sub-c", "name": "C", "folder": {}},
                        {
                            "id": "file-a",
                            "name": "AB-100.xlsx",
                            "webUrl": "https://example.com/a/ab-100",
                            "file": {},
                        },
                    ]
                },
            )
        if path.endswith("/items/sub-b/children"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "sub-c", "name": "C duplicate", "folder": {}},
                        {
                            "id": "file-b",
                            "name": "AB-100.xlsm",
                            "webUrl": "https://example.com/b/ab-100",
                            "file": {},
                        },
                    ]
                },
            )
        if path.endswith("/items/sub-c/children"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "file-c",
                            "name": "CD-200.xlsx",
                            "webUrl": "https://example.com/c/cd-200",
                            "file": {},
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": {"code": "itemNotFound"}})

    service = SharePointService(
        configured_settings(), transport=httpx.MockTransport(handler)
    )

    result = service.search_many(("AB-100", "CD-200"))

    assert result["AB-100"].status == "multiple"
    assert set(result["AB-100"].candidates) == {"AB-100.xlsx", "AB-100.xlsm"}
    assert result["CD-200"].status == "found"
    assert result["CD-200"].url == "https://example.com/c/cd-200"
    assert sum(path.endswith("/items/sub-c/children") for path in requested_paths) == 1
