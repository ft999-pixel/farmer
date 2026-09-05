"""Contract tests for the browser-only subsidy application flow."""

from fastapi.testclient import TestClient

from aidstation.api import app


client = TestClient(app)
ALLOWED_TYPES = {"completion", "submission", "form_submission"}


def _rounds(program):
    for variant in program.get("variants", []):
        for round_data in variant.get("rounds", []):
            yield variant, round_data


def test_every_program_round_has_typed_tasks_and_valid_dependencies():
    rows = client.get("/programs").json()
    assert rows
    for row in rows:
        detail = client.get(f"/programs/{row['id']}").json()
        rounds = list(_rounds(detail))
        assert rounds, detail["id"]
        for variant, round_data in rounds:
            tasks = round_data.get("tasks") or []
            assert tasks, f"{detail['id']} / {variant['id']} needs an application task"
            ids = {task["id"] for task in tasks}
            assert len(ids) == len(tasks)
            for task in tasks:
                assert task.get("title")
                assert task.get("description")
                assert task.get("status_type") in ALLOWED_TYPES
                assert set(task.get("depends_on") or []).issubset(ids)


def test_supported_hero_round_uses_form_submission_task():
    detail = client.get("/programs/farm-machine-115").json()
    labor = next(variant for variant in detail["variants"] if variant["id"] == "labor-saving")
    round_data = labor["rounds"][0]
    submit = next(task for task in round_data["tasks"] if task["id"] == "submit-application")
    assert submit["status_type"] == "form_submission"
    assert round_data["form_template_id"] == "farm_machine_115.labor_saving"


def test_application_and_program_pages_are_served_with_flow_assets():
    applications = client.get("/app/applications.html")
    program = client.get("/app/program.html?id=farm-machine-115&variant_id=labor-saving&round_id=farm-machine-115-labor-saving-2026")
    form = client.get("/app/form.html?application_id=missing")
    assert applications.status_code == 200
    assert "application-store.js" in applications.text
    assert program.status_code == 200
    assert "開始申請" in program.text
    assert form.status_code == 200
    assert "complete-application" in form.text
    prefill = client.get("/app/form-prefill.js").text
    assert "overlay-control" in prefill
    assert "請先完成前一項" not in prefill
