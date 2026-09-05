"""測試共用設定：src 加入模組路徑；卡點統計庫改寫到暫存檔，不污染 data/blockers.jsonl。"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# import aidstation.api 會載入 .env，把 ANTHROPIC_API_KEY 帶進 process env。
# 這發生在測試執行中途（誰先 import 誰先觸發），而 module-scope 的 fixture
# （例如 test_township.py 的 flow）比 function-scope 的 autouse fixture 更早建立，
# 所以只靠下面那個 fixture 擋不住——Flow 已經帶著真金鑰做好 ClaudeExtractor 了。
# 症狀就是「單獨跑會過、全套跑會掛」，而且每次掛的地方不一樣。
#
# 這裡先把值設成空字串：load_dotenv() 預設 override=False，看到 key 已存在就不覆蓋，
# 於是不論誰在什麼時候 import api，抽取器都會是關鍵字式的。
os.environ["ANTHROPIC_API_KEY"] = ""


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
