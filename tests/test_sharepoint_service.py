from urllib.parse import unquote

import httpx

from app.config import Settings
from app.services.sharepoint_service import (
    SharePointNumericInspectionService,
    SharePointService,
)


def configured_settings() -> Settings:
    return Settings(
        microsoft_tenant_id="tenant-id",
        microsoft_client_id="client-id",
        microsoft_client_secret="client-secret",
        sharepoint_drive_id="drive-id",
        sharepoint_folder_id="folder-id",
        sharepoint_numeric_inspection_drive_id=None,
        sharepoint_numeric_inspection_folder_id=None,
        sharepoint_numeric_inspection_url=None,
        sharepoint_shipping_inspection_url=None,
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

    assert result["AB-100"].status == "multiple"
    assert [candidate.name for candidate in result["AB-100"].candidates] == [
        "AB-100.xlsx",
        "AB-100-1.xlsx",
    ]
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
    assert {candidate.name for candidate in result["AB-100"].candidates} == {
        "AB-100.xlsx",
        "AB-100.xlsm",
    }
    assert {candidate.location for candidate in result["AB-100"].candidates} == {
        "A",
        "B",
    }
    assert result["CD-200"].status == "found"
    assert result["CD-200"].url == "https://example.com/c/cd-200"
    assert result["CD-200"].candidates[0].location == "A/C"
    assert sum(path.endswith("/items/sub-c/children") for path in requested_paths) == 1


def test_sharepoint_prefers_active_exact_part_numbers_over_related_suffixes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "file-1",
                        "name": "AB-100-1.xlsx",
                        "webUrl": "https://example.com/ab-100-1",
                        "file": {},
                    },
                    {
                        "id": "file-2",
                        "name": "AB-100-1-2.xlsx",
                        "webUrl": "https://example.com/ab-100-1-2",
                        "file": {},
                    },
                    {
                        "id": "file-3",
                        "name": "AB-100-1-10.xlsx",
                        "webUrl": "https://example.com/ab-100-1-10",
                        "file": {},
                    },
                    {
                        "id": "file-4",
                        "name": "AB-100-1-01.xlsx",
                        "webUrl": "https://example.com/ab-100-1-01",
                        "file": {},
                    },
                ]
            },
        )

    service = SharePointService(
        configured_settings(), transport=httpx.MockTransport(handler)
    )

    result = service.search_many(("AB-100", "AB-100-1"))

    assert result["AB-100"].status == "not_found"
    assert result["AB-100-1"].status == "multiple"
    assert [candidate.name for candidate in result["AB-100-1"].candidates] == [
        "AB-100-1.xlsx",
        "AB-100-1-2.xlsx",
        "AB-100-1-10.xlsx",
    ]


def test_numeric_inspection_matches_only_configured_part_number_boundaries() -> None:
    filenames = [
        "AB-12.xlsx",
        "AB-12_検査.xlsx",
        "AB-12-測定.pdf",
        "AB-12 測定値.xlsx",
        "AB-12　全角.xlsx",
        "AB-12・寸法.xlsx",
        "AB-123.xlsx",
        "AB-12ABC.xlsx",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": f"file-{index}",
                        "name": filename,
                        "webUrl": f"https://example.com/{index}",
                        "file": {},
                    }
                    for index, filename in enumerate(filenames)
                ]
            },
        )

    settings = configured_settings()
    settings.sharepoint_numeric_inspection_folder_id = "numeric-folder-id"
    service = SharePointNumericInspectionService(
        settings,
        transport=httpx.MockTransport(handler),
    )

    result = service.search_many(("AB-12",))

    assert result["AB-12"].status == "multiple"
    matched_names = [
        candidate.name for candidate in result["AB-12"].candidates
    ]
    assert matched_names[0] == "AB-12.xlsx"
    assert matched_names[1:] == sorted(filenames[1:6])
    assert "AB-123.xlsx" not in matched_names
    assert "AB-12ABC.xlsx" not in matched_names


def test_numeric_inspection_prefers_the_longest_active_part_number() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "file-1",
                        "name": "AB-12_検査.xlsx",
                        "webUrl": "https://example.com/file-1",
                        "file": {},
                    }
                ]
            },
        )

    settings = configured_settings()
    settings.sharepoint_numeric_inspection_folder_id = "numeric-folder-id"
    service = SharePointNumericInspectionService(
        settings,
        transport=httpx.MockTransport(handler),
    )

    result = service.search_many(("AB", "AB-12"))

    assert result["AB"].status == "not_found"
    assert result["AB-12"].status == "found"


def test_numeric_inspection_resolves_the_configured_shipping_folder_url() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "token"})
        requested_paths.append(unquote(request.url.path))
        if request.url.path.endswith("/drives/drive-id/root"):
            return httpx.Response(
                200,
                json={
                    "id": "drive-root",
                    "webUrl": (
                        "https://example.sharepoint.com/sites/hinshou/"
                        "Shared%20Documents"
                    ),
                },
            )
        if "/root:/" in request.url.path:
            return httpx.Response(
                200,
                json={"id": "shipping-folder", "folder": {}},
            )
        if request.url.path.endswith("/items/shipping-folder/children"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "file-1",
                            "name": "AB-12_検査.xlsx",
                            "webUrl": "https://example.com/file-1",
                            "file": {},
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": {"code": "itemNotFound"}})

    settings = configured_settings()
    settings.sharepoint_numeric_inspection_folder_id = None
    settings.sharepoint_shipping_inspection_url = (
        "https://example.sharepoint.com/sites/hinshou/Shared%20Documents/"
        "Forms/AllItems.aspx?id=%2Fsites%2Fhinshou%2FShared%20Documents"
        "%2F%E5%87%BA%E8%8D%B7%E6%A4%9C%E6%9F%BB%E8%A1%A8"
    )
    service = SharePointNumericInspectionService(
        settings,
        transport=httpx.MockTransport(handler),
    )

    result = service.search("AB-12")

    assert result.status == "found"
    assert result.url == "https://example.com/file-1"
    assert any(path.endswith("/root:/出荷検査表") for path in requested_paths)
