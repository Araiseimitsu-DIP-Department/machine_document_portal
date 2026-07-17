import json
from datetime import datetime
from pathlib import Path

from app.schemas.dashboard import DashboardData, DocumentState, MachineCard
from app.utils.machine_sort import sort_machines
from app.utils.part_number import normalize_part_number


class SampleDataError(RuntimeError):
    pass


class SampleDataService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_dashboard(self) -> DashboardData:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SampleDataError("サンプルデータを読み込めませんでした") from exc

        updated_at = datetime.fromisoformat(data["last_updated_at"])
        defaults = data.get("defaults", {})
        overrides = data.get("overrides", {})
        machines: list[MachineCard] = []
        display_order = 0

        for group in data["groups"]:
            for number in range(1, int(group["count"]) + 1):
                display_order += 1
                machine_id = f"{group['name']}-{number}"
                override = overrides.get(machine_id, {})
                format_values = {
                    "group": group["name"],
                    "number": number,
                    "machine_id": machine_id,
                }

                def resolved(name: str, fallback: object = None) -> object:
                    value = override[name] if name in override else defaults.get(name, fallback)
                    return value.format(**format_values) if isinstance(value, str) else value

                part_number = resolved("part_number")
                inspection_data = {
                    **defaults.get("inspection", {}),
                    **override.get("inspection", {}),
                }
                drawing_data = {
                    **defaults.get("drawing", {}),
                    **override.get("drawing", {}),
                }
                for document in (inspection_data, drawing_data):
                    if isinstance(document.get("url"), str):
                        document["url"] = document["url"].format(**format_values)
                machines.append(
                    MachineCard(
                        machine_id=machine_id,
                        group_name=group["name"],
                        machine_number=number,
                        display_order=display_order,
                        group_color=group["color"],
                        part_number=part_number,
                        normalized_part_number=normalize_part_number(part_number),
                        product_name=resolved("product_name"),
                        production_status=resolved(
                            "production_status", "稼働中" if part_number else None
                        ),
                        inspection=DocumentState(**inspection_data) if part_number else DocumentState(),
                        drawing=DocumentState(**drawing_data) if part_number else DocumentState(),
                        updated_at=datetime.fromisoformat(override["updated_at"])
                        if override.get("updated_at")
                        else updated_at,
                        stale=bool(override.get("stale", False)),
                    )
                )

        return DashboardData(
            machines=sort_machines(machines),
            last_updated_at=updated_at,
            source_label="サンプルデータ",
            notice="外部サービスには接続していません。画面確認用データを表示しています。",
        )
