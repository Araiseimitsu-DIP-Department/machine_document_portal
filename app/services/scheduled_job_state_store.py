from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from app.services.next_day_sheet_service import SheetTarget


logger = logging.getLogger(__name__)
NotificationStatus = Literal["pending", "completed", "ambiguous"]


class ScheduledJobStateStore:
    """Persist notification and per-part printing state for idempotent daily jobs."""

    def __init__(self, path: Path, *, spreadsheet_id: str | None) -> None:
        self.path = path
        self.spreadsheet_id = spreadsheet_id or ""
        self._lock = RLock()

    def record_daily_target(self, run_date: date, target: SheetTarget) -> str:
        with self._lock:
            state = self._load()
            target_key = self.target_key(target)
            state["daily_targets"][run_date.isoformat()] = target_key
            state["targets"].setdefault(
                target_key,
                {
                    "target_date": target.target_date.isoformat(),
                    "sheet_id": target.sheet_id,
                    "sheet_name": target.sheet_name,
                    "notification_status": "pending",
                    "notification_completed_at": None,
                    "printing_completed": False,
                    "printing_completed_at": None,
                    "printed_part_numbers": [],
                },
            )
            self._save(state)
            return target_key

    def target_for_run_date(self, run_date: date) -> tuple[str, SheetTarget] | None:
        with self._lock:
            state = self._load()
            target_key = state["daily_targets"].get(run_date.isoformat())
            record = state["targets"].get(target_key) if target_key else None
            if not isinstance(record, dict):
                return None
            try:
                target = SheetTarget(
                    target_date=date.fromisoformat(str(record["target_date"])),
                    sheet_id=int(record["sheet_id"]),
                    sheet_name=str(record["sheet_name"]),
                )
            except (KeyError, TypeError, ValueError):
                logger.warning("Scheduled job state contains an invalid target")
                return None
            return str(target_key), target

    def notification_status(self, target_key: str) -> NotificationStatus:
        with self._lock:
            record = self._target_record(self._load(), target_key)
            candidate = record.get("notification_status", "pending")
            if candidate in {"completed", "ambiguous"}:
                return candidate
            return "pending"

    def mark_notification(self, target_key: str, status: NotificationStatus) -> None:
        with self._lock:
            state = self._load()
            record = self._target_record(state, target_key)
            record["notification_status"] = status
            record["notification_completed_at"] = (
                datetime.now(timezone.utc).isoformat() if status == "completed" else None
            )
            self._save(state)

    def printed_part_numbers(self, target_key: str) -> set[str]:
        with self._lock:
            record = self._target_record(self._load(), target_key)
            values = record.get("printed_part_numbers", [])
            return {str(value) for value in values if isinstance(value, str)}

    def mark_part_printed(self, target_key: str, part_number: str) -> None:
        with self._lock:
            state = self._load()
            record = self._target_record(state, target_key)
            values = record.setdefault("printed_part_numbers", [])
            if part_number not in values:
                values.append(part_number)
            self._save(state)

    def printing_completed(self, target_key: str) -> bool:
        with self._lock:
            record = self._target_record(self._load(), target_key)
            return bool(record.get("printing_completed", False))

    def mark_printing_completed(self, target_key: str) -> None:
        with self._lock:
            state = self._load()
            record = self._target_record(state, target_key)
            record["printing_completed"] = True
            record["printing_completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save(state)

    def target_key(self, target: SheetTarget) -> str:
        source = "|".join(
            (
                self.spreadsheet_id,
                target.target_date.isoformat(),
                str(target.sheet_id),
                target.sheet_name,
            )
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    def _target_record(state: dict[str, Any], target_key: str) -> dict[str, Any]:
        record = state["targets"].get(target_key)
        if not isinstance(record, dict):
            raise KeyError(f"Unknown scheduled target: {target_key}")
        return record

    def _load(self) -> dict[str, Any]:
        empty = {"version": 1, "daily_targets": {}, "targets": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return empty
        except (OSError, ValueError):
            logger.exception("Scheduled job state could not be read")
            return empty
        if not isinstance(payload, dict):
            return empty
        daily_targets = payload.get("daily_targets")
        targets = payload.get("targets")
        if not isinstance(daily_targets, dict) or not isinstance(targets, dict):
            return empty
        return {"version": 1, "daily_targets": daily_targets, "targets": targets}

    def _save(self, state: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError:
            logger.exception("Scheduled job state could not be saved")
            raise
