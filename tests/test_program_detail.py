"""補助詳情 API：確保回得出完整白話內容，且能序列化。

rebase 到新的資料模型後，load_programs 改回傳 Pydantic 的 LoadedProgram，
直接回傳會 500。這組測試釘住轉換行為，避免詳情頁再次整頁壞掉。
"""
import pytest
from fastapi.testclient import TestClient

from aidstation.api import app

client = TestClient(app)
SAMPLE = "moa-disaster-cash-sample-2026"


def test_詳情回得出來而且是合法json():
    r = client.get(f"/programs/{SAMPLE}")
    assert r.status_code == 200
    assert r.json()["id"] == SAMPLE


def test_詳情頁要用的欄位都在():
    d = client.get(f"/programs/{SAMPLE}").json()
    for key in ("name", "authority", "documents", "window", "plain"):
        assert key in d, f"詳情頁需要 {key}"
    plain = d["plain"]
    assert plain["summary"]                      # 白話摘要
    assert len(plain["who"]) >= 1                # 誰可以申請
    assert len(plain["steps"]) >= 1              # 怎麼辦理
    assert len(plain["notes"]) >= 1              # 提醒


def test_文件要寫清楚去哪拿():
    docs = client.get(f"/programs/{SAMPLE}").json()["documents"]
    assert docs, "至少要有一項應備文件"
    assert all(d.get("where") for d in docs), "每項文件都要說明去哪拿"


def test_有承辦單位與電話():
    a = client.get(f"/programs/{SAMPLE}").json()["authority"]
    assert a.get("office") and a.get("tel")


def test_找不到的補助回404():
    assert client.get("/programs/does-not-exist").status_code == 404


@pytest.mark.parametrize("program_id", [
    "afa-crop-insurance-sample",
    "afa-green-payment-enrollment",
    "moa-occupational-injury",
    "moa-retirement-savings",
])
def test_其餘補助也都回得出詳情(program_id):
    r = client.get(f"/programs/{program_id}")
    assert r.status_code == 200
    assert r.json()["plain"]["summary"]


def test_清單附帶找補助頁要用的欄位():
    rows = client.get("/programs").json()
    assert rows
    row = next(r for r in rows if r["id"] == SAMPLE)
    assert row["display"]["ui_category"]         # 篩選用
    assert row["summary"]                        # 卡片上的一句話
    assert row["authority"]["office"]
