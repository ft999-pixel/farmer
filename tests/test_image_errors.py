"""公文照片辨識失敗時，要講真話並給對的下一步。

實際測試時，額度用完的錯誤被統一講成「辨識服務暫時不通，請稍後再試」。
但額度要到下個月才恢復，「稍後再試」是假話——農民會一直重按，
然後以為系統壞了、或以為自己做錯，最後放棄。

不同的失敗要分開講，關鍵是「還能不能再試」。
"""
import pytest

from aidstation.document import _read_image_error


class _Fake(Exception):
    """假造模型端的錯誤訊息，不需要真的打 API。"""


# ---- 不可重試：要引導改用貼上文字 ---------------------------------------

@pytest.mark.parametrize("message", [
    "Error code: 400 - You have reached your specified API usage limits.",
    "Your credit balance is too low to access the API.",
    "quota exceeded for this organization",
])
def test_額度用完不可以叫人稍後再試(message):
    text = _read_image_error(_Fake(message))
    assert "稍後再試" not in text, "額度用完再試也沒用，不能這樣講"
    assert "貼上文字" in text, "要告訴他還有哪條路可以走"


@pytest.mark.parametrize("message", [
    "authentication_error: invalid x-api-key",
    "Error code: 401",
])
def test_金鑰問題要說需要管理者處理(message):
    text = _read_image_error(_Fake(message))
    assert "管理者" in text
    assert "貼上文字" in text


def test_模型代號錯誤要說需要管理者處理():
    text = _read_image_error(_Fake("not_found_error: model not found"))
    assert "管理者" in text


# ---- 可重試：不要把人趕走 ------------------------------------------------

def test_流量過大要叫人等一下再試():
    text = _read_image_error(_Fake("rate_limit_error: 429 too many requests"))
    assert "再" in text and "試" in text
    assert "貼上文字" not in text, "這是暫時的，不需要叫他換方法"


def test_網路問題要叫人等一下再試():
    text = _read_image_error(_Fake("APIConnectionError: connection failed"))
    assert "網路" in text
    assert "貼上文字" not in text


# ---- 共通 ----------------------------------------------------------------

def test_未知錯誤仍要給出路():
    text = _read_image_error(_Fake("something entirely unexpected"))
    assert "貼上文字" in text


@pytest.mark.parametrize("message", [
    "You have reached your specified API usage limits.",
    "rate_limit_error 429",
    "APIConnectionError",
    "weird failure",
])
def test_訊息不可以有英文技術術語(message):
    """農民看不懂 quota、rate limit、API。"""
    text = _read_image_error(_Fake(message))
    for word in ("quota", "rate limit", "API", "error", "Error", "token"):
        assert word not in text, f"訊息裡不該出現「{word}」：{text}"
