import re
from collections.abc import Iterable
from typing import Protocol, TypeVar


class MachineLike(Protocol):
    machine_id: str
    group_name: str
    machine_number: int
    display_order: int


MachineT = TypeVar("MachineT", bound=MachineLike)
_MACHINE_PATTERN = re.compile(r"^(.+?)[-_\s]?(\d+)$")


def parse_machine_id(machine_id: str) -> tuple[str, int]:
    match = _MACHINE_PATTERN.match(machine_id.strip())
    if not match:
        return machine_id.strip().upper(), 0
    return match.group(1).strip().upper(), int(match.group(2))


def machine_sort_key(machine: MachineLike) -> tuple[str, int, int, str]:
    group = machine.group_name.strip().upper()
    number = machine.machine_number
    if not group or number < 1:
        parsed_group, parsed_number = parse_machine_id(machine.machine_id)
        group = group or parsed_group
        number = number if number >= 1 else parsed_number
    return group, number, machine.display_order, machine.machine_id


def sort_machines(machines: Iterable[MachineT]) -> list[MachineT]:
    return sorted(machines, key=machine_sort_key)
