"""測試共用設定：src 加入模組路徑；卡點統計庫改寫到暫存檔，不污染 data/blockers.jsonl。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _isolate_blocker_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AIDSTATION_BLOCKERS", str(tmp_path / "blockers.jsonl"))
