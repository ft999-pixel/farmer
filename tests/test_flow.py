"""對話流程測試：一次一題、5 題收斂、我卡住了、公文收文日流程。"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation.flow import (MAX_QUESTIONS, STUCK_BUTTON, STUCK_REASONS, Flow,
                             Session)

TODAY = date(2026, 8, 10)


def make_flow() -> Flow:
    return Flow(today=TODAY)


def test_full_conversation_converges():
    """「阮的檨仔攏落了了」→ 逐題回答 → 最多 5 題內出結果。"""
    flow, s = make_flow(), Session()
    reply = flow.handle_text(s, "阮的檨仔攏落了了")
    answers = {"township": "玉井區", "loss_rate": "超過一半", "land_tenure": "口頭講好的",
               "policy_enrolled_2y": "有", "is_farming": "有", "insured_farmer": "有",
               "land_doc": "都沒有", "age": "58"}
    rounds = 0
    while s.pending_field is not None and rounds <= MAX_QUESTIONS:
        rounds += 1
        reply = flow.handle_text(s, answers.get(s.pending_field, "不確定"))
    assert rounds <= MAX_QUESTIONS
    # 措辭鐵則（2026-08-12）：不出現「符合／不符合／資格」判定字眼
    assert "✅ 建議優先看｜農業天然災害現金救助" in reply.text
    assert "符合｜" not in reply.text.replace("可能符合", "")
    assert "免附（豁免條款）" in reply.text          # 口頭租約＋登錄 → 豁免
    assert "實際資格由承辦單位認定" in reply.text
    assert reply.options == [STUCK_BUTTON]
    # 結構化 payload：網頁端畫卡片用
    assert reply.payload["kind"] == "results"
    assert len(reply.payload["tiers"]["priority"]) >= 1


def test_one_question_at_a_time():
    flow, s = make_flow(), Session()
    reply = flow.handle_text(s, "阮的檨仔攏落了了")
    assert reply.text.count("？") <= 1  # 一次只問一題
    assert s.pending_field is not None


def test_stuck_button_gives_help_not_survey():
    """「我卡住了」→ 三選項 → 給協助文字。"""
    flow, s = make_flow(), Session()
    reply = flow.handle_text(s, STUCK_BUTTON)
    assert reply.options == STUCK_REASONS
    reply2 = flow.handle_text(s, "文件生不出來")
    assert "公所" in reply2.text or "農會" in reply2.text  # 給協助，不是問卷


def test_document_flow_asks_received_date_then_calc():
    """公文流程：文到型 → 問收文日 → 回計算式。"""
    flow, s = make_flow(), Session()
    text = ("主旨：請於文到7日內檢具佐證資料到府說明。\n"
            "說明：逾期未補正者，駁回其申請。")
    reply = flow.handle_document_text(s, text)
    assert "哪一天收到" in reply.text
    assert s.pending_doc is not None
    reply2 = flow.handle_text(s, "8/5")
    assert "8/5 收到 ＋ 7日 ＝ 8/12 前" in reply2.text
    assert s.pending_doc is None
    assert STUCK_BUTTON in (reply2.options or [])


def test_document_flow_explicit_date_no_question():
    """公告型公文：有明確日期 → 不問收文日，直接倒數。"""
    flow, s = make_flow(), Session()
    reply = flow.handle_document_text(s, "主旨：請於115年8月20日前向本所提出申請。")
    assert s.pending_doc is None
    assert "剩 10 天" in reply.text
