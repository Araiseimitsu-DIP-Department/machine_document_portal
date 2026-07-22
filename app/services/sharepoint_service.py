from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.google_drive_service import (
    DocumentCandidateResult,
    DocumentSearchResult,
)


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
    location: str | None = None


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

    def search(self, part_number: str) -> DocumentSearchResult:
        """Look up exact and numbered related filename stems for one part number."""

        return self.search_many((part_number,)).get(
            part_number,
            DocumentSearchResult(status="not_checked"),
        )

    def search_many(
        self, part_numbers: Iterable[str]
    ) -> dict[str, DocumentSearchResult]:
        """Match literal part numbers and positive-integer filename suffixes."""

        part_numbers = {
            part_number
            for part_number in part_numbers
            if part_number
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
                filename_stem = PurePath(file.name).stem
                if filename_stem in part_numbers:
                    matches[filename_stem].append(file)
                    continue
                for part_number in part_numbers:
                    prefix = f"{part_number}-"
                    if not filename_stem.startswith(prefix):
                        continue
                    suffix = filename_stem[len(prefix) :]
                    if re.fullmatch(r"[1-9][0-9]*", suffix):
                        matches[part_number].append(file)
                        break
            return {
                part_number: self._result_for_matches(
                    part_number,
                    matches[part_number],
                )
                for part_number in part_numbers
            }

        return {
            part_number: DocumentSearchResult(status=status)
            for part_number in part_numbers
        }

    @staticmethod
    def _result_for_matches(
        part_number: str,
        matches: list[_SharePointFile],
    ) -> DocumentSearchResult:
        if not matches:
            return DocumentSearchResult(status="not_found")
        matches.sort(
            key=lambda file: SharePointService._match_sort_key(part_number, file)
        )
        candidates = tuple(
            DocumentCandidateResult(
                name=file.name,
                url=file.url,
                location=file.location,
            )
            for file in matches
        )
        if len(matches) > 1:
            return DocumentSearchResult(
                status="multiple",
                candidates=candidates,
            )
        return DocumentSearchResult(
            status="found",
            url=matches[0].url,
            candidates=candidates,
        )

    @staticmethod
    def _match_sort_key(
        part_number: str,
        file: _SharePointFile,
    ) -> tuple[int, int, str, str, str]:
        filename_stem = PurePath(file.name).stem
        if filename_stem == part_number:
            return (0, 0, file.name, file.location or "", file.url)
        suffix = filename_stem[len(part_number) + 1 :]
        return (1, int(suffix), file.name, file.location or "", file.url)

    def _list_files(self) -> list[_SharePointFile]:
        with httpx.Client(timeout=15.0, transport=self.transport) as client:
            token = self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            drive_id = quote(self.settings.sharepoint_drive_id or "", safe="")
            root_folder_id = self.settings.sharepoint_folder_id or ""
            pending_folders = deque([(root_folder_id, "")])
            visited_folder_ids: set[str] = set()
            files: list[_SharePointFile] = []

            while pending_folders:
                folder_id, folder_location = pending_folders.popleft()
                if folder_id in visited_folder_ids:
                    continue
                visited_folder_ids.add(folder_id)
                encoded_folder_id = quote(folder_id, safe="")
                next_url: str | None = (
                    f"{self.graph_base_url}/drives/{drive_id}/items/"
                    f"{encoded_folder_id}/children"
                )
                params: dict[str, str] | None = {
                    "$select": "id,name,webUrl,file,folder",
                    "$top": "999",
                }

                while next_url:
                    response = self._get(
                        client,
                        next_url,
                        headers=headers,
                        params=params,
                    )
                    payload = self._json(response)
                    for item in payload.get("value", []):
                        if not isinstance(item, dict):
                            continue
                        item_id = item.get("id")
                        if "folder" in item and isinstance(item_id, str):
                            if item_id not in visited_folder_ids:
                                folder_name = item.get("name")
                                child_location = folder_location
                                if isinstance(folder_name, str) and folder_name:
                                    child_location = "/".join(
                                        value
                                        for value in (folder_location, folder_name)
                                        if value
                                    )
                                pending_folders.append((item_id, child_location))
                            continue
                        if "file" not in item:
                            continue
                        name = item.get("name")
                        web_url = item.get("webUrl")
                        if isinstance(name, str) and isinstance(web_url, str):
                            files.append(
                                _SharePointFile(
                                    name=name,
                                    url=web_url,
                                    location=folder_location or None,
                                )
                            )
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
