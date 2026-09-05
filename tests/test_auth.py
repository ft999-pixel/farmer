"""帳號與統一登入：角色寫在帳號上，由系統決定去處。

要釘住的重點：
- 農民與承辦人員用同一個登入表單，去哪一頁由帳號的角色決定
- 密碼不以明碼儲存
- 農民不能自己註冊出管理權限
"""
import pytest
from fastapi.testclient import TestClient

from aidstation import auth as auth_mod

ADMIN_PW = "admin-secret-pw"
FARMER_PW = "farmer-pw-123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PW)
    monkeypatch.setenv("ADMIN_USERNAME", "承辦小張")
    monkeypatch.setenv("AIDSTATION_ACCOUNTS_DB", str(tmp_path / "accounts.db"))
    monkeypatch.setenv("AIDSTATION_MEMBERS_DB", str(tmp_path / "members.db"))
    from aidstation.api import app
    return TestClient(app)


# ---- 密碼處理 ------------------------------------------------------------

def test_密碼不以明碼儲存():
    stored = auth_mod.hash_password("my-password")
    assert "my-password" not in stored
    assert auth_mod.verify_password("my-password", stored)
    assert not auth_mod.verify_password("wrong", stored)


def test_同一組密碼每次雜湊結果不同():
    """有加鹽，兩個人用同密碼看起來也不一樣。"""
    assert auth_mod.hash_password("same") != auth_mod.hash_password("same")


# ---- 註冊 ----------------------------------------------------------------

def test_農民註冊後直接進我的資料(client):
    r = client.post("/auth/register", json={"username": "阿明伯", "password": FARMER_PW})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "member"
    assert body["redirect"] == "profile.html"
    assert client.get("/members/me").json()["logged_in"] is True


def test_註冊不能取得管理權限(client):
    """農民自己註冊出來的一律是 member，不能碰後臺。"""
    client.post("/auth/register", json={"username": "想當管理員", "password": FARMER_PW})
    assert auth_mod.get_account("想當管理員")["role"] == "member"
    assert client.get("/admin/programs").status_code in (401, 403)


def test_帳號重複要擋(client):
    client.post("/auth/register", json={"username": "阿明伯", "password": FARMER_PW})
    assert client.post("/auth/register",
                       json={"username": "阿明伯", "password": "another"}).status_code == 409


def test_密碼太短要擋(client):
    r = client.post("/auth/register", json={"username": "阿明伯", "password": "123"})
    assert r.status_code == 422


def test_帳號格式不合要擋(client):
    for bad in ("", "a", "x" * 40, "有 空白"):
        assert client.post("/auth/register",
                           json={"username": bad, "password": FARMER_PW}).status_code == 422


# ---- 登入分派 ------------------------------------------------------------

def test_同一個表單_農民與承辦人員各自到該去的地方(client):
    client.post("/auth/register", json={"username": "阿明伯", "password": FARMER_PW})
    client.post("/auth/logout")

    farmer = client.post("/auth/login", json={"username": "阿明伯", "password": FARMER_PW})
    assert farmer.json()["redirect"] == "profile.html"
    client.post("/auth/logout")

    boss = client.post("/auth/login", json={"username": "承辦小張", "password": ADMIN_PW})
    assert boss.json()["role"] == "admin"
    assert boss.json()["redirect"] == "admin.html"
    assert client.get("/admin/programs").status_code == 200


def test_承辦帳號由env自動建立(client):
    """.env 設好就能直接登入，不必先註冊。"""
    r = client.post("/auth/login", json={"username": "承辦小張", "password": ADMIN_PW})
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_密碼錯誤與帳號不存在回同一句話(client):
    """避免被拿來探測哪些帳號存在。"""
    client.post("/auth/register", json={"username": "阿明伯", "password": FARMER_PW})
    a = client.post("/auth/login", json={"username": "阿明伯", "password": "wrong"})
    b = client.post("/auth/login", json={"username": "不存在的人", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_登入失敗不會給任何權限(client):
    client.post("/auth/login", json={"username": "承辦小張", "password": "wrong"})
    assert client.get("/members/me").json()["logged_in"] is False
    assert client.get("/admin/programs").status_code in (401, 403)


def test_whoami回報目前角色(client):
    assert client.get("/auth/me").json()["logged_in"] is False
    client.post("/auth/register", json={"username": "阿明伯", "password": FARMER_PW})
    me = client.get("/auth/me").json()
    assert me["role"] == "member" and me["username"] == "阿明伯"


def test_登出會同時清掉兩種身分(client):
    client.post("/auth/login", json={"username": "承辦小張", "password": ADMIN_PW})
    client.post("/auth/logout")
    assert client.get("/auth/me").json()["logged_in"] is False
    assert client.get("/admin/programs").status_code in (401, 403)
