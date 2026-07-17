from app.schemas.dashboard import MachineCard
from app.utils.machine_sort import parse_machine_id, sort_machines


def machine(machine_id: str) -> MachineCard:
    group, number = parse_machine_id(machine_id)
    return MachineCard(
        machine_id=machine_id,
        group_name=group,
        machine_number=number,
    )


def test_machine_ids_are_sorted_numerically() -> None:
    values = [machine("C-10"), machine("C-2"), machine("C-12"), machine("C-1")]
    assert [item.machine_id for item in sort_machines(values)] == ["C-1", "C-2", "C-10", "C-12"]


def test_groups_are_sorted_before_machine_number() -> None:
    values = [machine("B-1"), machine("A-5"), machine("A-1")]
    assert [item.machine_id for item in sort_machines(values)] == ["A-1", "A-5", "B-1"]
