"""啟動 ngrok 通道：python scripts\\start_ngrok.py

從 .env 讀 NGROK_AUTHTOKEN（只需設定一次），
自動註冊 token 並以固定網址開通道到本機 8000 埠。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_URL = "unplanted-giver-uninvited.ngrok-free.dev"  # 你的 ngrok 固定網址

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

token = os.environ.get("NGROK_AUTHTOKEN", "").strip()
# 自動修復常見貼錯：整串「export NGROK_AUTHTOKEN=xxx」或帶引號貼進來
if "NGROK_AUTHTOKEN=" in token:
    token = token.split("NGROK_AUTHTOKEN=")[-1]
token = token.replace("export", "").strip().strip('"\'')
if not token or "$" in token:
    print("請先在 .env 加一行：NGROK_AUTHTOKEN=你的token")
    print("（token 在 dashboard.ngrok.com 左側「Your Authtoken」頁，按複製鈕）")
    sys.exit(1)

# 找 ngrok：PATH 沒有的話，去 winget 的安裝位置找（舊終端機 PATH 未更新時）
ngrok = shutil.which("ngrok")
if ngrok is None:
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ngrok.exe"
    if candidate.exists():
        ngrok = str(candidate)
if ngrok is None:
    print("找不到 ngrok。請開一個新的終端機（右上角＋）再執行本腳本，或重新安裝 ngrok。")
    sys.exit(1)

subprocess.run([ngrok, "config", "add-authtoken", token], check=True)
print(f"✓ token 已設定，開通道中… LINE Webhook URL 填：https://{STATIC_URL}/line/webhook")

# 新版 ngrok 用 --url，舊版（如 winget 的 3.3.1）用 --domain；都失敗就開隨機網址
for args in ([ngrok, "http", f"--url={STATIC_URL}", "8000"],
             [ngrok, "http", f"--domain={STATIC_URL}", "8000"]):
    result = subprocess.run(args)
    if result.returncode == 0:
        sys.exit(0)
print("固定網址開不起來，改開隨機網址（記得把畫面上的新網址更新到 LINE 後台）…")
subprocess.run([ngrok, "http", "8000"])
