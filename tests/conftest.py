"""測試共用設定：src 加入模組路徑；卡點統計庫改寫到暫存檔，不污染 data/blockers.jsonl。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _isolate_blocker_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDSTATION_BLOCKERS", str(tmp_path / "blockers.jsonl"))


@pytest.fixture(autouse=True)
def _no_live_api_calls(monkeypatch):
    """測試不打真的 API。

    import api.py 會順手載入 .env；金鑰一旦出現，抽取器就換成模型式的，
    於是同一批測試「單獨跑會過、全套跑會掛」，而且每次都要等網路。
    測試結果不該取決於本機有沒有 .env。
    模型式路徑改用注入假抽取器來測（見 test_township.py）。
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
