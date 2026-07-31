from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Literal
from urllib.parse import parse_qs, quote, unquote, urlsplit

import httpx

from app.config import Settings
from app.services.document_search import (
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


@dataclass(frozen=True, slots=True)
class _SharePointLocation:
    drive_id: str | None
    folder_id: str | None
    folder_url: str | None = None


class SharePointService:
    """Find inspection sheets in one configured SharePoint folder via Graph."""

    graph_base_url = "https://graph.microsoft.com/v1.0"
    _NUMERIC_INSPECTION_SEPARATORS = frozenset(("_", "-", " ", "　", "・"))

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        location: _SharePointLocation | None = None,
        match_mode: Literal["numbered_suffix", "delimited_prefix"] = "numbered_suffix",
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.location = location or _SharePointLocation(
            drive_id=settings.sharepoint_drive_id,
            folder_id=settings.sharepoint_folder_id,
        )
        self.match_mode = match_mode

    @property
    def configured(self) -> bool:
        return all(
            (
                self.settings.microsoft_tenant_id,
                self.settings.microsoft_client_id,
                self.settings.microsoft_client_secret,
                self.location.drive_id,
                self.location.folder_id or self.location.folder_url,
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
        """Match files using the configured filename rule."""

        part_numbers = tuple(
            dict.fromkeys(
                part_number for part_number in part_numbers if part_number
            )
        )
        if not part_numbers:
            return {}
        part_number_set = set(part_numbers)
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
                matched_part_number = self._matched_part_number(
                    filename_stem,
                    part_number_set,
                )
                if matched_part_number is not None:
                    matches[matched_part_number].append(file)
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

    def _matched_part_number(
        self,
        filename_stem: str,
        part_number_set: set[str],
    ) -> str | None:
        if filename_stem in part_number_set:
            return filename_stem
        if self.match_mode == "delimited_prefix":
            related_part_numbers = (
                filename_stem[:index]
                for index, character in enumerate(filename_stem)
                if character in self._NUMERIC_INSPECTION_SEPARATORS
                and filename_stem[:index] in part_number_set
            )
            return max(related_part_numbers, key=len, default=None)

        related_part_number, separator, suffix = filename_stem.rpartition("-")
        if (
            separator
            and related_part_number in part_number_set
            and suffix.isascii()
            and suffix.isdigit()
            and not suffix.startswith("0")
        ):
            return related_part_number
        return None

    def _result_for_matches(
        self,
        part_number: str,
        matches: list[_SharePointFile],
    ) -> DocumentSearchResult:
        if not matches:
            return DocumentSearchResult(status="not_found")
        matches.sort(
            key=lambda file: self._match_sort_key(part_number, file)
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

    def _match_sort_key(
        self,
        part_number: str,
        file: _SharePointFile,
    ) -> tuple[int, int | str, str, str, str]:
        filename_stem = PurePath(file.name).stem
        if filename_stem == part_number:
            return (0, 0, file.name, file.location or "", file.url)
        if self.match_mode == "delimited_prefix":
            return (1, file.name, file.name, file.location or "", file.url)
        suffix = filename_stem[len(part_number) + 1 :]
        return (1, int(suffix), file.name, file.location or "", file.url)

    def _list_files(self) -> list[_SharePointFile]:
        with httpx.Client(timeout=15.0, transport=self.transport) as client:
            token = self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            drive_id = quote(self.location.drive_id or "", safe="")
            root_folder_id = self._root_folder_id(
                client,
                drive_id,
                headers=headers,
            )
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

    def _root_folder_id(
        self,
        client: httpx.Client,
        drive_id: str,
        *,
        headers: dict[str, str],
    ) -> str:
        if self.location.folder_id:
            return self.location.folder_id
        folder_url = self.location.folder_url
        if not folder_url:
            raise SharePointRequestError("SharePoint folder is not configured")

        target_url = urlsplit(folder_url)
        query_folder_path = parse_qs(target_url.query).get("id", [None])[0]
        target_path = unquote(query_folder_path or target_url.path).rstrip("/")

        root_response = self._get(
            client,
            f"{self.graph_base_url}/drives/{drive_id}/root",
            headers=headers,
            params={"$select": "id,webUrl"},
        )
        root_payload = self._json(root_response)
        root_id = root_payload.get("id")
        root_web_url = root_payload.get("webUrl")
        if not isinstance(root_id, str) or not isinstance(root_web_url, str):
            raise SharePointRequestError("Microsoft Graph returned invalid drive metadata")

        root_path = unquote(urlsplit(root_web_url).path).rstrip("/")
        if target_path == root_path:
            return root_id
        root_prefix = root_path + "/"
        if not target_path.startswith(root_prefix):
            raise SharePointRequestError(
                "SharePoint folder URL is outside the configured drive"
            )
        relative_path = target_path[len(root_prefix) :]
        encoded_relative_path = quote(relative_path, safe="/")
        folder_response = self._get(
            client,
            (
                f"{self.graph_base_url}/drives/{drive_id}/root:/"
                f"{encoded_relative_path}"
            ),
            headers=headers,
            params={"$select": "id,folder"},
        )
        folder_payload = self._json(folder_response)
        folder_id = folder_payload.get("id")
        if not isinstance(folder_id, str) or "folder" not in folder_payload:
            raise SharePointRequestError(
                "Microsoft Graph did not return the configured folder"
            )
        return folder_id

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


class SharePointNumericInspectionService(SharePointService):
    """Find numeric-inspection files by a literal part number and separator."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            settings,
            transport=transport,
            location=_SharePointLocation(
                drive_id=(
                    settings.sharepoint_numeric_inspection_drive_id
                    or settings.sharepoint_drive_id
                ),
                folder_id=settings.sharepoint_numeric_inspection_folder_id,
                folder_url=(
                    settings.sharepoint_numeric_inspection_url
                    or settings.sharepoint_shipping_inspection_url
                ),
            ),
            match_mode="delimited_prefix",
        )
