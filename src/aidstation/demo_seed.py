"""示範帳號：讓部署站也能直接 demo。

Render 免費方案的磁碟是暫時性的，而 data/*.db 又刻意不進版控（那是使用者資料），
所以部署站每次重新部署後帳號表都是空的，示範帳號 push 不上去。
這裡在啟動時依 web/demo-persona.json 重建，讓部署站不必手動註冊。

開關就是 DEMO_PASSWORD 這個環境變數本身：沒設就完全不做事——跟
auth.ensure_admin_account() 讀 ADMIN_PASSWORD 是同一個模式。密碼不寫在程式碼或
版控裡，才不會有一組「預設密碼」隨著 repo 一起公開。

⚠️ 設了 DEMO_PASSWORD 等於在公開網址上開一個已知帳密的帳號。裡面全是編造的
   資料，角色也只是一般會員（拿不到後台），但仍請只在示範站啟用。

個資（姓名、身分證、住址、地號）永遠不會寫進資料庫——那是 PrivateFormProfile，
只能由瀏覽器的「載入示範資料」按鈕寫進 localStorage。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import auth, members
from .schemas import MatchingProfile

PERSONA_FILE = Path(__file__).resolve().parents[2] / "web" / "demo-persona.json"


def load_personas(path: Path | None = None) -> list[dict]:
    source = path or PERSONA_FILE
    if not source.is_file():
        return []
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    personas = data.get("personas")
    return [p for p in personas if isinstance(p, dict) and p.get("account")] \
        if isinstance(personas, list) else []


def seed_persona(persona: dict, password: str) -> str:
    """建立或更新一個示範帳號，回傳做了什麼（建立／更新）。"""
    account = str(persona["account"])
    profile = persona.get("matching_profile") or {}

    # 同一道防線：媒合資料若混進 PrivateFormProfile 欄位，這裡就會丟例外，
    # 不會等到示範當天才發現個資被寫進資料庫。
    MatchingProfile.model_validate(profile)

    if auth.get_account(account) is None:
        auth.create_account(account, password, auth.ROLE_MEMBER)
        action = "建立"
    else:
        with auth._connect() as conn:
            conn.execute(
                "UPDATE accounts SET password_hash = ?, role = ? WHERE username = ?",
                (auth.hash_password(password), auth.ROLE_MEMBER, account))
        action = "更新"

    members.save_member(account, profile)
    return action


def ensure_demo_accounts(password: str | None = None,
                         path: Path | None = None) -> list[str]:
    """啟動時呼叫。沒有 DEMO_PASSWORD 就什麼都不做，回傳建好的帳號名稱。"""
    password = password or os.environ.get("DEMO_PASSWORD") or ""
    if len(password) < auth.MIN_PASSWORD:
        return []
    seeded = []
    for persona in load_personas(path):
        try:
            seed_persona(persona, password)
        except Exception:
            # 示範資料壞掉不該讓整個服務起不來
            continue
        seeded.append(str(persona["account"]))
    return seeded
