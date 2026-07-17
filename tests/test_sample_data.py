from app.config import PROJECT_ROOT
from app.services.sample_data_service import SampleDataService


def dashboard():
    return SampleDataService(PROJECT_ROOT / "sample_data" / "machines.json").load_dashboard()


def by_id(machine_id: str):
    return next(machine for machine in dashboard().machines if machine.machine_id == machine_id)


def test_sample_data_contains_all_configured_machines() -> None:
    data = dashboard()
    assert len(data.machines) == 61
    assert data.machines[0].machine_id == "A-1"
    assert data.machines[-1].machine_id == "F-14"


def test_sample_data_covers_required_states() -> None:
    assert by_id("A-1").inspection.available and by_id("A-1").drawing.available
    assert by_id("A-2").inspection.status == "not_found"
    assert by_id("A-3").drawing.status == "not_found"
    assert by_id("A-4").inspection.status == by_id("A-4").drawing.status == "not_found"
    assert by_id("A-5").has_production is False
    assert by_id("B-4").drawing.status == "multiple"
    assert by_id("B-1").inspection.status == "auth_error"
    assert by_id("B-2").drawing.status == "api_error"
    assert by_id("B-3").stale is True
