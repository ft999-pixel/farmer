"""後台測試：驗證擋關、路徑穿越、備份與稽核、存檔即生效。

重點不是「能不能存」，而是「存不進去的東西真的存不進去」——
後台放行的資料若能讓啟動載入失敗，整站就會起不來。
"""
import json

import pytest
from fastapi.testclient import TestClient

from aidstation import admin
from aidstation.knowledge import validate_program

PASSWORD = "test-pw-1234"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """把後台的資料目錄導到暫存區，不動到真的 data/programs。"""
    programs = tmp_path / "programs"
    programs.mkdir()
    sample = {
        "id": "test-program", "name": "測試補助", "category": "災害救助",
        "authority": {"level": "中央", "agency": "農糧署"},
        "eligibility": {"all": [{"field": "crop", "op": "in", "value": ["芒果"]}]},
        "source": {"status": "sample", "last_verified": "2026-08-10"},
    }
    (programs / "test-program.json").write_text(
        json.dumps(sample, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(admin, "PROGRAMS_DIR", programs)
    monkeypatch.setattr(admin, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(admin, "AUDIT_LOG", tmp_path / "audit.jsonl")
    monkeypatch.setattr(admin, "reload_runtime", lambda: 1)   # 不動全域 app 狀態
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)

    from aidstation.api import app
    return TestClient(app)


def login(client):
    r = client.post("/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200


def test_未登入一律擋下():
    from aidstation.api import app
    c = TestClient(app)
    for path in ("/admin/programs", "/admin/schema", "/admin/program/test-program"):
        assert c.get(path).status_code in (401, 503)


def test_密碼錯誤不給進(client):
    assert client.post("/admin/login", json={"password": "wrong"}).status_code == 401
    assert client.get("/admin/programs").status_code == 401


def test_登入後可讀清單與明細(client):
    login(client)
    rows = client.get("/admin/programs").json()
    assert rows[0]["id"] == "test-program"
    assert rows[0]["stale"] is False         # 剛覆核過，不該標警示
    assert client.get("/admin/program/test-program").json()["name"] == "測試補助"


def test_超過半年沒覆核要標待覆核():
    from datetime import date, timedelta
    today = date.today()
    assert admin._is_stale((today - timedelta(days=400)).isoformat()) is True
    assert admin._is_stale((today - timedelta(days=30)).isoformat()) is False
    assert admin._is_stale(None) is True      # 沒填也算待覆核
    assert admin._is_stale("不是日期") is True


def test_存檔會備份舊檔並寫稽核(client):
    login(client)
    p = client.get("/admin/program/test-program").json()
    p["name"] = "改過的名字"
    r = client.post("/admin/program/test-program", json={"program": p})
    assert r.status_code == 200
    assert r.json()["backup"]                                  # 有備份檔名
    assert (admin.BACKUP_DIR / r.json()["backup"]).exists()    # 檔案真的在
    assert client.get("/admin/program/test-program").json()["name"] == "改過的名字"
    audit = client.get("/admin/audit").json()
    assert audit[0]["action"] == "update" and audit[0]["name"] == "改過的名字"


def test_未註冊欄位擋在存檔前_檔案不動(client):
    login(client)
    p = client.get("/admin/program/test-program").json()
    p["eligibility"] = {"all": [{"field": "不存在的欄位", "op": "=", "value": 1}]}
    r = client.post("/admin/program/test-program", json={"program": p})
    assert r.status_code == 422
    assert any("未註冊欄位" in e for e in r.json()["detail"]["errors"])
    # 原檔沒被改動
    assert client.get("/admin/program/test-program").json()["name"] == "測試補助"


def test_不合法運算子擋下(client):
    login(client)
    p = client.get("/admin/program/test-program").json()
    p["eligibility"] = {"all": [{"field": "crop", "op": "≈", "value": "芒果"}]}
    r = client.post("/admin/program/test-program", json={"program": p})
    assert r.status_code == 422
    assert any("運算子" in e for e in r.json()["detail"]["errors"])


def test_id_不合法擋下路徑穿越(client):
    login(client)
    r = client.post("/admin/program/..%2F..%2Fevil", json={"program": {"id": "x"}})
    assert r.status_code in (404, 422)
    r = client.get("/admin/program/UPPER_case")
    assert r.status_code == 422


def test_網址與內容的_id_不一致要擋(client):
    login(client)
    p = client.get("/admin/program/test-program").json()
    p["id"] = "another-id"
    r = client.post("/admin/program/test-program", json={"program": p})
    assert r.status_code == 422


def test_檔名與id不同時仍能編輯_且不會產生第二個檔(client):
    """既有資料的檔名不等於 id（如 disaster-cash-sample.json / moa-...-2026）。
    存檔必須覆寫原檔，否則會多出一筆同 id 的補助。"""
    odd = admin.PROGRAMS_DIR / "檔名跟id不一樣.json"
    odd.write_text(json.dumps({
        "id": "weird-named", "name": "怪檔名",
        "eligibility": {"all": [{"field": "crop", "op": "=", "value": "芒果"}]},
        "source": {"status": "sample"},
    }, ensure_ascii=False), encoding="utf-8")
    login(client)

    p = client.get("/admin/program/weird-named").json()
    assert p["name"] == "怪檔名"
    p["name"] = "改名成功"
    assert client.post("/admin/program/weird-named", json={"program": p}).status_code == 200

    assert not (admin.PROGRAMS_DIR / "weird-named.json").exists()   # 沒有另開新檔
    assert json.loads(odd.read_text(encoding="utf-8"))["name"] == "改名成功"
    ids = [r["id"] for r in client.get("/admin/programs").json()]
    assert ids.count("weird-named") == 1


def test_新增補助會以id命名新檔(client):
    login(client)
    new = {"id": "brand-new-aid", "name": "全新補助",
           "eligibility": {"all": [{"field": "crop", "op": "=", "value": "芒果"}]},
           "source": {"status": "official", "last_verified": "2026-09-01"}}
    r = client.post("/admin/program/brand-new-aid", json={"program": new})
    assert r.status_code == 200 and r.json()["created"] is True
    assert r.json()["backup"] is None
    assert (admin.PROGRAMS_DIR / "brand-new-aid.json").exists()


def test_刪除會備份並記稽核(client):
    login(client)
    r = client.delete("/admin/program/test-program")
    assert r.status_code == 200 and r.json()["backup"]
    assert client.get("/admin/program/test-program").status_code == 404
    assert client.get("/admin/audit").json()[0]["action"] == "delete"


def test_後台放行的資料_啟動載入一定過(client):
    """後台與啟動共用同一套驗證，這裡釘住這個保證。"""
    login(client)
    p = client.get("/admin/program/test-program").json()
    p["name"] = "新名字"
    assert client.post("/admin/program/test-program", json={"program": p}).status_code == 200
    from aidstation.fields import load_fields
    saved = json.loads((admin.PROGRAMS_DIR / "test-program.json").read_text(encoding="utf-8"))
    assert validate_program(saved, load_fields()) == []
