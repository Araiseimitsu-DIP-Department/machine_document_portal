from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.google_drive_service import DocumentSearchResult
from app.utils.part_number import normalize_part_number


class SharePointError(Exception):
    """Base error for the SharePoint read-only integration."""


class SharePointAuthenticationError(SharePointError):
    """The application could not obtain a Microsoft Graph access token."""


class SharePointPermissionError(SharePointError):
    """The configured application cannot read the target SharePoint folder."""


class SharePointRequestError(SharePointError):
    """Microsoft Graph could not complete a request."""


@dataclass(frozen=True, slots=True)
class _SharePointFile:
    name: str
    url: str


class SharePointService:
    """Find inspection sheets in one configured SharePoint folder via Graph."""

    graph_base_url = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return all(
            (
                self.settings.microsoft_tenant_id,
                self.settings.microsoft_client_id,
                self.settings.microsoft_client_secret,
                self.settings.sharepoint_drive_id,
                self.settings.sharepoint_folder_id,
            )
        )

    def search(self, normalized_part_number: str) -> DocumentSearchResult:
        """Look up one exact filename stem for callers that need a single result."""

        return self.search_many((normalized_part_number,)).get(
            normalize_part_number(normalized_part_number),
            DocumentSearchResult(status="not_checked"),
        )

    def search_many(
        self, normalized_part_numbers: Iterable[str]
    ) -> dict[str, DocumentSearchResult]:
        """Match filename stems to part numbers after one folder-list request."""

        part_numbers = {
            normalize_part_number(part_number)
            for part_number in normalized_part_numbers
            if part_number and normalize_part_number(part_number)
        }
        if not part_numbers:
            return {}
        if not self.configured:
            return {
                part_number: DocumentSearchResult(status="not_checked")
                for part_number in part_numbers
            }

        try:
            files = self._list_files()
        except SharePointAuthenticationError:
            status = "auth_error"
        except SharePointPermissionError:
            status = "permission_error"
        except SharePointError:
            status = "api_error"
        else:
            matches: dict[str, list[_SharePointFile]] = defaultdict(list)
            for file in files:
                filename_stem = normalize_part_number(PurePath(file.name).stem)
                if filename_stem in part_numbers:
                    matches[filename_stem].append(file)
            return {
                part_number: self._result_for_matches(matches[part_number])
                for part_number in part_numbers
            }

        return {
            part_number: DocumentSearchResult(status=status)
            for part_number in part_numbers
        }

    @staticmethod
    def _result_for_matches(matches: list[_SharePointFile]) -> DocumentSearchResult:
        if not matches:
            return DocumentSearchResult(status="not_found")
        if len(matches) > 1:
            return DocumentSearchResult(
                status="multiple", candidates=tuple(file.name for file in matches)
            )
        return DocumentSearchResult(status="found", url=matches[0].url)

    def _list_files(self) -> list[_SharePointFile]:
        with httpx.Client(timeout=15.0, transport=self.transport) as client:
            token = self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            drive_id = quote(self.settings.sharepoint_drive_id or "", safe="")
            folder_id = quote(self.settings.sharepoint_folder_id or "", safe="")
            next_url: str | None = (
                f"{self.graph_base_url}/drives/{drive_id}/items/{folder_id}/children"
            )
            params: dict[str, str] | None = {
                "$select": "id,name,webUrl,file",
                "$top": "999",
            }
            files: list[_SharePointFile] = []

            while next_url:
                response = self._get(client, next_url, headers=headers, params=params)
                payload = self._json(response)
                for item in payload.get("value", []):
                    if not isinstance(item, dict) or "file" not in item:
                        continue
                    name = item.get("name")
                    web_url = item.get("webUrl")
                    if isinstance(name, str) and isinstance(web_url, str):
                        files.append(_SharePointFile(name=name, url=web_url))
                candidate = payload.get("@odata.nextLink")
                next_url = candidate if isinstance(candidate, str) else None
                params = None
            return files

    def _access_token(self, client: httpx.Client) -> str:
        tenant_id = quote(self.settings.microsoft_tenant_id or "", safe="")
        try:
            response = client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": self.settings.microsoft_client_id or "",
                    "client_secret": self.settings.microsoft_client_secret or "",
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
        except httpx.RequestError as exc:
            raise SharePointRequestError("Microsoft Graph token request could not be sent") from exc
        if response.status_code in {400, 401}:
            raise SharePointAuthenticationError("Microsoft Graph token request failed")
        if response.is_error:
            raise SharePointRequestError("Microsoft Graph token request failed")
        token = self._json(response).get("access_token")
        if not isinstance(token, str) or not token:
            raise SharePointAuthenticationError("Microsoft Graph did not return an access token")
        return token

    @staticmethod
    def _get(
        client: httpx.Client,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None,
    ) -> httpx.Response:
        try:
            response = client.get(url, headers=headers, params=params)
        except httpx.RequestError as exc:
            raise SharePointRequestError("Microsoft Graph request could not be sent") from exc
        if response.status_code == 401:
            raise SharePointAuthenticationError("Microsoft Graph rejected the access token")
        if response.status_code == 403:
            raise SharePointPermissionError("Microsoft Graph denied folder access")
        if response.is_error:
            raise SharePointRequestError("Microsoft Graph folder request failed")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SharePointRequestError("Microsoft Graph returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SharePointRequestError("Microsoft Graph returned an invalid response")
        return payload
