"""金鑰檢查：在你自己的電腦執行，驗證 .env 裡的金鑰是否可用。

執行：python scripts/check_keys.py
只顯示 ✓／✗ 與原因，不會顯示金鑰內容。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    print("請先安裝套件：pip install -r requirements.txt")
    sys.exit(1)


def check_anthropic() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("✗ ANTHROPIC_API_KEY 未設定（.env 裡沒填）")
        return
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
            max_tokens=10, messages=[{"role": "user", "content": "回覆OK"}])
        print(f"✓ Anthropic 金鑰可用（模型回覆：{msg.content[0].text.strip()[:10]}）")
    except Exception as e:
        name = type(e).__name__
        hint = ""
        if "Authentication" in name:
            hint = "→ 金鑰無效或已撤銷，請到 console.anthropic.com 重新確認"
        elif "credit" in str(e).lower() or "billing" in str(e).lower():
            hint = "→ 帳戶額度不足，請到 console.anthropic.com 儲值"
        print(f"✗ Anthropic：{name} {hint}")


def check_line() -> None:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        print("✗ LINE_CHANNEL_ACCESS_TOKEN 未設定")
        return
    try:
        import httpx
        r = httpx.get("https://api.line.me/v2/bot/info",
                      headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if r.status_code == 200:
            print(f"✓ LINE token 可用（官方帳號：{r.json().get('displayName')}）")
        elif r.status_code == 401:
            print("✗ LINE token 無效 → 到 LINE Developers 的 Messaging API 頁籤重新發行")
        else:
            print(f"✗ LINE 回應 HTTP {r.status_code}：{r.text[:80]}")
    except Exception as e:
        print(f"✗ LINE 連線失敗：{type(e).__name__}")
    if not os.environ.get("LINE_CHANNEL_SECRET"):
        print("✗ LINE_CHANNEL_SECRET 未設定（webhook 簽章驗證需要）")


if __name__ == "__main__":
    print("=== 農民補給站 金鑰檢查 ===")
    check_anthropic()
    check_line()
