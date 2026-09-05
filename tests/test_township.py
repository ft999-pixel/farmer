"""鄉鎮比對：農民講得籠統，不等於他不符合。

實際測試時發現：農民說「我在台南種芒果」，回答鄉鎮時打「台南」，
災害救助會被判成「不符合」而從結果中消失。
農民只是講到縣市層級，系統卻直接把他排除——這是假陰性，
比查不到更糟，因為他會就此放棄申請。
"""
from datetime import date

import pytest

from aidstation.flow import Flow, Session

TODAY = date(2026, 9, 6)   # 示範公告受理期間內
DISASTER = "農業天然災害現金救助"


@pytest.fixture(scope="module")
def flow():
    return Flow(today=TODAY)


# ---- 鄉鎮字串比對 --------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("玉井區", "玉井區"),
    ("玉井", "玉井區"),       # 少寫「區」
    ("南化", "南化區"),
    ("楠西鎮", "楠西區"),     # 寫錯後綴
])
def test_鄉鎮少寫或寫錯後綴仍認得(flow, text, expected):
    matched, county_only = flow._match_township(text)
    assert matched == expected
    assert county_only is False


@pytest.mark.parametrize("text", ["台南", "臺南市", "彰化", "彰化縣", "高雄"])
def test_縣市層級要標記為需要再問(flow, text):
    matched, county_only = flow._match_township(text)
    assert matched is None
    assert county_only is True, f"{text} 是縣市，應標記為還要再問哪一區"


@pytest.mark.parametrize("text", ["員林市", "斗六市", "頭份市"])
def test_縣轄市不可誤判為縣市(flow, text):
    """員林市、斗六市是鄉鎮層級的縣轄市，不能因為結尾是「市」就當成縣市。"""
    _, county_only = flow._match_township(text)
    assert county_only is False


# ---- 整段對話 ------------------------------------------------------------

def _run(flow, township):
    s = Session()
    flow.handle_text(s, "我在台南種芒果 都被颱風吹壞了")
    reply = None
    for answer in [township, "超過一半", "我的", "有", "有", "58"]:
        reply = flow.handle_text(s, answer)
        payload = reply.payload or {}
        if payload.get("tiers"):
            return payload["tiers"]
    return {}


def _tier_of(tiers, name):
    for tier in ("priority", "maybe", "skip"):
        if any(name in c.get("name", "") for c in tiers.get(tier, [])):
            return tier
    return None


def test_答完整鄉鎮會被優先推薦(flow):
    assert _tier_of(_run(flow, "玉井區"), DISASTER) == "priority"


def test_答少寫區的鄉鎮也要推薦(flow):
    assert _tier_of(_run(flow, "玉井"), DISASTER) == "priority"


def test_只答縣市不可被排除(flow):
    """這是原始的錯誤：答「台南」時災害救助整個消失。"""
    tier = _tier_of(_run(flow, "台南"), DISASTER)
    assert tier is not None, "災害救助不該從結果中消失"
    assert tier != "skip", "只講到縣市不足以判定不符合"


def test_縣市層級會提示補充是哪一區(flow):
    s = Session()
    flow.handle_text(s, "我在台南種芒果 都被颱風吹壞了")
    reply = flow.handle_text(s, "台南")
    assert "哪一個區" in reply.text
    assert "玉井區" in reply.text      # 要告訴他有哪些選項


# ---- 從整句話裡認出鄉鎮 --------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("我在台南玉井的芒果都被颱風吹壞了", "玉井區"),
    ("我在楠西種芒果", "楠西區"),
    ("南化區的芒果掉了", "南化區"),
])
def test_第一句就認得出鄉鎮(flow, text, expected):
    assert flow._township_in_text(text) == expected


@pytest.mark.parametrize("text", ["我在台南種芒果", "我在彰化種水稻", "芒果被吹壞了"])
def test_句子裡沒有鄉鎮就不要亂猜(flow, text):
    assert flow._township_in_text(text) is None


def test_講了鄉鎮就不該再問一次(flow):
    """使用者已經說「台南玉井」，還反問「你的田在哪個鄉鎮」是重複勞動。"""
    s = Session()
    reply = flow.handle_text(s, "我在台南玉井的芒果都被颱風吹壞了")
    assert s.facts.get("township") == "玉井區"
    assert "哪個鄉鎮" not in reply.text


# ---- 抽取器直接給出縣市的情況 --------------------------------------------
#
# 正式站有設 API 金鑰，用的是模型式抽取器，它會把「台南」直接寫進 township。
# 正規化原本只在回答問題時才跑，這條路整個繞過檢查，補助一樣會消失。
# 這裡用假抽取器重現，不需要網路，也不受本機有沒有 .env 影響。

class _FakeExtractor:
    """模擬模型式抽取器：把縣市層級的地名直接放進 township。"""

    def __init__(self, result):
        self._result = result

    def extract(self, text):
        return dict(self._result)


def _flow_with(result):
    f = Flow(today=TODAY)
    f.extractor = _FakeExtractor(result)
    return f


def test_抽取器給縣市時要改成反問而不是排除():
    f = _flow_with({"crop": "芒果", "event": "天然災害", "township": "台南"})
    s = Session()
    reply = f.handle_text(s, "我在台南種芒果 都被颱風吹壞了")
    assert "township" not in s.facts, "縣市層級不該直接當成鄉鎮存進去"
    assert "哪個鄉鎮" in reply.text


def test_抽取器給縣市但句子裡有鄉鎮時要救回來():
    f = _flow_with({"crop": "芒果", "event": "天然災害", "township": "台南"})
    s = Session()
    f.handle_text(s, "我在台南玉井的芒果都被颱風吹壞了")
    assert s.facts.get("township") == "玉井區"


def test_抽取器給少寫區的鄉鎮要補正():
    f = _flow_with({"crop": "芒果", "event": "天然災害", "township": "玉井"})
    s = Session()
    f.handle_text(s, "我在玉井種芒果")
    assert s.facts.get("township") == "玉井區"


def test_抽取器給公告外的鄉鎮要保留():
    """中埔鄉是合法鄉鎮，只是不在公告內——要留著讓比對判定不符合，不能丟掉。"""
    f = _flow_with({"crop": "芒果", "event": "天然災害", "township": "中埔鄉"})
    s = Session()
    f.handle_text(s, "我在中埔種芒果")
    assert s.facts.get("township") == "中埔鄉"


def test_抽取器給縣市時災害救助不可消失():
    f = _flow_with({"crop": "芒果", "event": "天然災害", "township": "台南"})
    s = Session()
    f.handle_text(s, "我在台南種芒果 都被颱風吹壞了")
    for answer in ["玉井", "超過一半", "我的", "有", "有", "58"]:
        reply = f.handle_text(s, answer)
        tiers = (reply.payload or {}).get("tiers")
        if tiers:
            assert _tier_of(tiers, DISASTER) == "priority"
            return
    pytest.fail("沒有給出結果")


def test_句子裡講了鄉鎮就能直接推薦(flow):
    s = Session()
    flow.handle_text(s, "我在台南玉井的芒果都被颱風吹壞了")
    for answer in ["超過一半", "我的", "有", "有", "58"]:
        reply = flow.handle_text(s, answer)
        tiers = (reply.payload or {}).get("tiers")
        if tiers:
            assert _tier_of(tiers, DISASTER) == "priority"
            return
    pytest.fail("五題內沒有給出結果")
