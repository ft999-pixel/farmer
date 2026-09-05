"""統一登入：由系統依憑證類型判斷身分與去處，使用者不必自己選入口。

規則：有填密碼＝承辦人員、沒填＝農民。
密碼錯誤必須直接擋下，不能默默降級成農民登入——那會讓人不知道自己是誰。
"""
import pytest
from fastapi.testclient import TestClient

from aidstation import admin as admin_mod
from aidstation import members as members_mod

PASSWORD = "test-admin-pw"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("AIDSTATION_MEMBERS_DB", str(tmp_path / "members.db"))
    from aidstation.api import app
    return TestClient(app)


def test_只填代號會被當成農民(client):
    r = client.post("/auth/login", json={"identifier": "阿明伯"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "member"
    assert body["redirect"] == "profile.html"
    assert body["created"] is True
    # 拿到的是會員 cookie，不是後臺的
    assert members_mod.COOKIE in r.cookies or members_mod.COOKIE in client.cookies


def test_第二次登入不會重複建立(client):
    client.post("/auth/login", json={"identifier": "阿明伯"})
    assert client.post("/auth/login", json={"identifier": "阿明伯"}).json()["created"] is False


def test_填了正確密碼會被當成承辦人員(client):
    r = client.post("/auth/login", json={"identifier": "王承辦", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "admin"
    assert body["redirect"] == "admin.html"
    # 真的能進後臺
    assert client.get("/admin/programs").status_code == 200


def test_密碼錯誤要擋下而不是降級成農民(client):
    r = client.post("/auth/login", json={"identifier": "王承辦", "password": "wrong"})
    assert r.status_code == 401
    # 不可以因此變成農民登入
    assert client.get("/members/me").json()["logged_in"] is False
    assert client.get("/admin/programs").status_code in (401, 403)


def test_農民登入不會拿到後臺權限(client):
    client.post("/auth/login", json={"identifier": "阿明伯"})
    assert client.get("/members/me").json()["logged_in"] is True
    assert client.get("/admin/programs").status_code in (401, 403)


def test_代號格式不合擋下(client):
    for bad in ("", "a", "x" * 40, "有 空白"):
        assert client.post("/auth/login", json={"identifier": bad}).status_code == 422
