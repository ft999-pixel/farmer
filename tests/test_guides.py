"""白話指南測試：Markdown 渲染的安全性與正確性、後台 CRUD。

最重要的一組是「原始 HTML 不能執行」——指南內容由後台輸入，
若能夾帶 <script>，看指南的農民就會被攻擊。
"""
import json

import pytest
from fastapi.testclient import TestClient

from aidstation import guides
from aidstation.guides import render_markdown

PASSWORD = "test-pw-1234"


# ---- Markdown 安全性 ------------------------------------------------------

def test_原始html不會被執行():
    html = render_markdown("<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html          # 變成畫面上的文字


def test_夾帶的標籤只會變成文字():
    """關鍵是「不會形成標籤」。onerror 以純文字出現無害，
    重點在 < 已跳脫成 &lt;，瀏覽器不會把它當成元素。"""
    html = render_markdown('<img src=x onerror="alert(1)">')
    assert "&lt;img" in html          # 跳脫過了
    assert "<img" not in html         # 沒有真的產生 img 元素

    # 只允許渲染器自己產生的標籤，使用者輸入不得新增任何元素
    import re
    tags = set(re.findall(r"<(/?\w+)", html))
    assert tags <= {"p", "/p"}


def test_javascript連結不放行():
    html = render_markdown("[點我](javascript:alert(1))")
    assert "javascript:" not in html
    assert "href" not in html                # 整個連結被拆掉，只留文字
    assert "點我" in html


def test_正常連結放行且加上安全屬性():
    html = render_markdown("[農業部](https://www.moa.gov.tw)")
    assert 'href="https://www.moa.gov.tw"' in html
    assert 'rel="noopener noreferrer"' in html


# ---- Markdown 正確性 ------------------------------------------------------

def test_標題轉換():
    assert "<h2>大標</h2>" in render_markdown("# 大標")
    assert "<h3>小標</h3>" in render_markdown("## 小標")


def test_粗體與段落():
    html = render_markdown("這是**重點**。\n\n第二段。")
    assert "<strong>重點</strong>" in html
    assert html.count("<p>") == 2


def test_條列與編號():
    ul = render_markdown("- 甲\n- 乙")
    assert ul.count("<li>") == 2 and "<ul>" in ul
    ol = render_markdown("1. 甲\n2. 乙")
    assert "<ol>" in ol and ol.count("<li>") == 2


def test_清單結束後要收尾():
    html = render_markdown("- 甲\n\n之後的段落")
    assert "</ul>" in html
    assert html.index("</ul>") < html.index("之後的段落")


def test_空內容不會爆():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""


# ---- 後台 CRUD ------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    store = tmp_path / "guides.json"
    store.write_text(json.dumps([{
        "id": "existing", "title": "既有指南", "category": "測試",
        "read_minutes": 3, "body": "內容", "updated_at": "2026-09-01",
    }], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("AIDSTATION_GUIDES", str(store))
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setattr("aidstation.admin.AUDIT_LOG", tmp_path / "audit.jsonl")
    from aidstation.api import app
    return TestClient(app)


def login(client):
    assert client.post("/admin/login", json={"password": PASSWORD}).status_code == 200


def test_公開清單不含內文(client):
    rows = client.get("/guides").json()
    assert rows[0]["title"] == "既有指南"
    assert "body" not in rows[0]             # 清單頁不需要，少傳一點


def test_單篇附渲染後的html(client):
    g = client.get("/guides/existing").json()
    assert "<p>內容</p>" in g["html"]


def test_找不到的指南回404(client):
    assert client.get("/guides/nope").status_code == 404


def test_沒登入不能改指南(client):
    assert client.post("/admin/guide/x", json={"guide": {}}).status_code in (401, 403)
    assert client.delete("/admin/guide/existing").status_code in (401, 403)
    assert client.get("/admin/guides").status_code in (401, 403)


def test_新增與更新(client):
    login(client)
    new = {"title": "新指南", "category": "測試", "read_minutes": 2, "body": "# 標題\n內文"}
    r = client.post("/admin/guide/new-one", json={"guide": new})
    assert r.status_code == 200 and r.json()["created"] is True
    assert client.get("/guides/new-one").json()["title"] == "新指南"

    r = client.post("/admin/guide/new-one", json={"guide": {**new, "title": "改過的"}})
    assert r.json()["created"] is False
    assert len(client.get("/guides").json()) == 2      # 沒有變成兩筆


def test_欄位不全擋下(client):
    login(client)
    r = client.post("/admin/guide/no-title", json={"guide": {"body": "有內文沒標題"}})
    assert r.status_code == 422
    assert any("標題" in e for e in r.json()["detail"]["errors"])

    r = client.post("/admin/guide/大寫中文", json={"guide": {"title": "x", "body": "y"}})
    assert r.status_code == 422


def test_刪除(client):
    login(client)
    assert client.delete("/admin/guide/existing").status_code == 200
    assert client.get("/guides/existing").status_code == 404
    assert client.delete("/admin/guide/existing").status_code == 404


def test_預覽與正式渲染一致(client):
    login(client)
    body = "# 標題\n**粗體**"
    preview = client.post("/admin/guide-preview", json={"body": body}).json()["html"]
    client.post("/admin/guide/same", json={"guide": {"title": "t", "body": body}})
    assert preview == client.get("/guides/same").json()["html"]
