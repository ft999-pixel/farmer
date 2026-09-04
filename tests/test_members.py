"""會員資料測試：存得回來、換裝置看得到、刪得掉、別人的資料看不到。

存了農民的資料就有責任：能刪除是底線，cookie 被竄改不能變成別人也是底線。
"""
import pytest
from fastapi.testclient import TestClient

from aidstation import members


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDSTATION_MEMBERS_DB", str(tmp_path / "members.db"))
    from aidstation.api import app
    return TestClient(app)


def login(client, code="阿明伯"):
    r = client.post("/members/login", json={"code": code})
    assert r.status_code == 200
    return r.json()


def test_第一次登入會建新的(client):
    assert login(client)["created"] is True
    assert login(client)["created"] is False      # 第二次是找回來，不是又建一個


def test_代號格式不合擋下(client):
    for bad in ("", "a", "x" * 40, "abc def", "王小明<script>"):
        assert client.post("/members/login", json={"code": bad}).status_code == 422


def test_存得起來也讀得回來(client):
    login(client)
    facts = {"crop": ["芒果", "文旦"], "township": "玉井區", "is_farming": True}
    contact = {"name": "王阿明", "tel": "0912-345-678"}
    client.post("/members/me", json={"contact": contact, "facts": facts})

    me = client.get("/members/me").json()
    assert me["logged_in"] is True
    assert me["facts"]["crop"] == ["芒果", "文旦"]     # 複選作物存得住
    assert me["contact"]["name"] == "王阿明"


def test_換裝置輸入同代號拿得回資料(client, tmp_path, monkeypatch):
    login(client, "阿明伯")
    client.post("/members/me", json={"contact": {}, "facts": {"township": "玉井區"}})

    from aidstation.api import app
    other = TestClient(app)                       # 另一台裝置：全新 cookie
    assert other.get("/members/me").json()["logged_in"] is False
    other.post("/members/login", json={"code": "阿明伯"})
    assert other.get("/members/me").json()["facts"]["township"] == "玉井區"


def test_沒登入不能存(client):
    assert client.post("/members/me", json={"contact": {}, "facts": {}}).status_code == 401
    assert client.delete("/members/me").status_code == 401
    assert client.get("/members/me").json()["logged_in"] is False


def test_竄改cookie不能變成別人(client):
    login(client, "阿明伯")
    client.post("/members/me", json={"contact": {}, "facts": {"township": "玉井區"}})
    client.post("/members/logout")

    # 直接把 cookie 換成別人的代號——簽章對不上，必須被拒絕
    forged = f"{'阿明伯'.encode().hex()}|9999999999|deadbeef"
    client.cookies.set(members.COOKIE, forged)
    assert client.get("/members/me").json()["logged_in"] is False


def test_過期的cookie不算數(client):
    expired = members._sign("阿明伯", 1)          # 1970 年就過期了
    client.cookies.set(members.COOKIE, expired)
    assert client.get("/members/me").json()["logged_in"] is False


def test_刪除是真的刪掉(client):
    login(client)
    client.post("/members/me", json={"contact": {}, "facts": {"township": "玉井區"}})
    assert client.delete("/members/me").json()["deleted"] is True
    assert members.get_member("阿明伯") is None    # 資料庫裡真的沒了
    assert client.get("/members/me").json()["logged_in"] is False
