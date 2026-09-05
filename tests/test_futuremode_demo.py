"""Hero Demo acceptance tests for the public matching and local-form seams."""
from fastapi.testclient import TestClient


HERO = {
    "applicant_type": "individual_farmer",
    "location": "屏東縣",
    "crops": ["香蕉"],
    "land_area_ha": 0.8,
    "farming_years": 1,
    "certifications": ["溯源農糧產品追溯條碼（QR Code）"],
    "intent": "想買電動割草機",
    "equipment_intent": "電動割草機",
}


def test_match_profile_asks_one_hero_question_and_returns_public_profile():
    from aidstation.api import app

    client = TestClient(app)
    response = client.post("/match", json={"profile": HERO, "today": "2026-08-20"})
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["crops"] == ["香蕉"]
    assert body["next_question"]["key"] == "machine_model_status"
    assert any(
        item["variant_id"] == "labor-saving" and item["status"] == "NEED_INFO"
        for item in body["results"]
    )
    assert "full_name" not in body["profile"]
    assert "bank_account" not in body["profile"]


def test_match_profile_never_accepts_private_form_values():
    from aidstation.api import app

    client = TestClient(app)
    for profile in (
        {"full_name": "王阿明"},
        {"location": "屏東縣", "form": {"bank_account": "123"}},
    ):
        assert client.post("/match", json={"profile": profile}).status_code == 422


def test_match_date_and_official_form_seam_are_deterministic():
    from aidstation.api import app

    client = TestClient(app)
    active = client.post("/match", json={"profile": HERO, "today": "2026-08-20"}).json()
    closed = client.post("/match", json={"profile": HERO, "today": "2026-09-05"}).json()
    active_labor = next(item for item in active["results"] if item["variant_id"] == "labor-saving")
    closed_labor = next(item for item in closed["results"] if item["variant_id"] == "labor-saving")
    assert active_labor["status"] == "NEED_INFO"
    assert closed_labor["status"] == "CLOSED"

    manifest = client.get("/official-forms/manifest")
    assert manifest.status_code == 200
    labor = next(item for item in manifest.json()["templates"]
                  if item["id"] == "farm_machine_115.labor_saving")
    assert "storage_scope" not in labor["fields"][0]
    assert client.get("/official-forms/pdf/labor_saving.pdf").status_code == 200


def test_chat_hero_recommendation_contains_tasks_and_local_form_id():
    from aidstation.api import app

    client = TestClient(app)
    sid = "hero-acceptance"
    client.post("/chat", json={"session_id": sid, "kind": "reset", "today": "2026-08-20"})
    question = client.post("/chat", json={
        "session_id": sid,
        "text": "我去年才回來屏東種香蕉，大概八分地，有 QR Code，最近想買電動割草機。",
        "today": "2026-08-20",
    })
    assert question.status_code == 200
    assert question.json()["options"] == ["有，在公告補助牌型內", "還沒有品牌或型號", "不確定"]

    result = client.post("/chat", json={
        "session_id": sid,
        "text": "有，在公告補助牌型內",
        "today": "2026-08-20",
    })
    body = result.json()
    assert body["payload"]["kind"] == "results"
    cards = body["payload"]["tiers"]["priority"] + body["payload"]["tiers"]["maybe"]
    labor = next(card for card in cards if card["variant_id"] == "labor-saving")
    assert labor["status"] == "MATCH"
    assert labor["form_template_id"] == "farm_machine_115.labor_saving"
    assert labor["tasks"]


def test_hero_static_pages_are_served_by_existing_app_mount():
    from aidstation.api import app

    client = TestClient(app)
    landing = client.get("/app/?demo=1")
    form = client.get("/app/form.html?program_id=farm-machine-115&variant_id=labor-saving")
    assert landing.status_code == 200
    assert form.status_code == 200
    assert "form-prefill.js" in form.text
