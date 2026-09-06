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
                assert "再繼續下一步" not in task["description"]
                assert "完成「" not in task["description"]
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
    assert "官方表單預覽" not in form.text
    prefill = client.get("/app/form-prefill.js").text
    assert "請先完成前一項" not in prefill
    assert "儲存表單後更新" not in prefill


def test_official_fields_are_edited_beside_the_sheet_not_on_it():
    """欄位在 PDF 旁邊分組編輯，PDF 上只疊唯讀文字。

    分組本身就是隱私說明：哪些只留在本機、哪些會同步、哪些只是這次草稿。
    直接在 PDF 的小格子上打字看不出這件事，所以 overlay 不放輸入框。
    """
    form = client.get("/app/form.html?application_id=missing")
    prefill = client.get("/app/form-prefill.js").text
    css = client.get("/app/form-prefill.css").text

    for container in ("draft-fields", "private-fields", "matching-fields", "helper-fields"):
        assert f'id="{container}"' in form.text, container
    assert 'id="official-overlay" aria-hidden="true"' in form.text

    assert "overlay-control" not in prefill, "PDF 上不應該再有可編輯的輸入框"
    assert "overlay-control" not in css
    assert "renderFieldGroup(privateFields" in prefill
    assert "renderFieldGroup(matchingFields" in prefill
    assert "renderFieldGroup(draftFields" in prefill
    assert "pointer-events: none" in css
