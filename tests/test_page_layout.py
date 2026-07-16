from app.routers.pages import build_overview_lanes
from app.schemas.dashboard import MachineCard


def group(name: str, count: int):
    return (
        name,
        [
            MachineCard(
                machine_id=f"{name}-{number}",
                group_name=name,
                machine_number=number,
            )
            for number in range(1, count + 1)
        ],
    )


def test_smallest_adjacent_groups_share_first_overview_lane() -> None:
    groups = [
        group("A", 6),
        group("B", 5),
        group("C", 12),
        group("D", 12),
        group("E", 14),
        group("F", 14),
    ]

    lanes = build_overview_lanes(groups, max_lanes=5)

    assert [[item[0] for item in lane] for lane in lanes] == [
        ["A", "B"],
        ["C"],
        ["D"],
        ["E"],
        ["F"],
    ]
