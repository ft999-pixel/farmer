"""示範帳號自動建立：部署站沒有資料庫，帳號要在啟動時重建。

兩件事一定要成立：
  1. 沒設 DEMO_PASSWORD 就完全不做事（正式站不會冒出一個已知帳密的帳號）
  2. 個資永遠不進資料庫，就算示範檔裡有寫
"""
import json

import pytest

from aidstation import auth, demo_seed, members


PERSONA = {
    "personas": [{
        "account": "demo-farmer",
        "label": "測試芒果農",
        "matching_profile": {"location": "玉井區", "crops": ["芒果"], "land_area_ha": 0.8},
        "private_form_profile": {"full_name": "王阿明", "national_id": "A123456789"},
    }]
}


@pytest.fixture
def persona_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDSTATION_ACCOUNTS_DB", str(tmp_path / "accounts.db"))
    monkeypatch.setenv("AIDSTATION_MEMBERS_DB", str(tmp_path / "members.db"))
    path = tmp_path / "demo-persona.json"
    path.write_text(json.dumps(PERSONA, ensure_ascii=False), encoding="utf-8")
    return path


def test_沒設密碼就完全不建帳號(persona_file, monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    assert demo_seed.ensure_demo_accounts(path=persona_file) == []
    assert auth.get_account("demo-farmer") is None


def test_太短的密碼一樣不建(persona_file):
    assert demo_seed.ensure_demo_accounts(password="123", path=persona_file) == []
    assert auth.get_account("demo-farmer") is None


def test_設了密碼就建得起來且可重複執行(persona_file):
    for _ in range(2):
        assert demo_seed.ensure_demo_accounts(password="demo1234",
                                              path=persona_file) == ["demo-farmer"]
    account = auth.get_account("demo-farmer")
    assert account["role"] == auth.ROLE_MEMBER
    assert auth.verify_password("demo1234", account["password_hash"])
    assert members.get_member("demo-farmer")["profile"]["crops"] == ["芒果"]


def test_個資不會被寫進資料庫(persona_file):
    """private_form_profile 只能留在瀏覽器，就算示範檔裡寫了也不能落庫。"""
    demo_seed.ensure_demo_accounts(password="demo1234", path=persona_file)
    stored = json.dumps(members.get_member("demo-farmer"), ensure_ascii=False)
    for leaked in ("王阿明", "A123456789", "full_name", "national_id"):
        assert leaked not in stored, leaked


def test_示範檔裡的媒合資料混進個資欄位就要擋下來(persona_file, tmp_path):
    bad = dict(PERSONA)
    bad["personas"] = [{
        "account": "bad-farmer",
        "matching_profile": {"location": "玉井區", "national_id": "A123456789"},
    }]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    assert demo_seed.ensure_demo_accounts(password="demo1234", path=path) == []
    assert auth.get_account("bad-farmer") is None
