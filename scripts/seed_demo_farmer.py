"""建立示範農民帳號：python scripts\\seed_demo_farmer.py [密碼]

讀 web\\demo-persona.json，把裡面的每個 persona 建成一個可登入的農民帳號，
並把 matching_profile 存進會員資料。密碼預設 demo1234，可用參數覆蓋。
重複執行沒關係：帳號已存在就只更新密碼與媒合資料。

private_form_profile（姓名、身分證、住址、電話、銀行帳號、地號）**不會**寫進
任何資料庫——那是 PrivateFormProfile，只能留在瀏覽器。示範時登入後到
「我的資料」頁按「載入示範資料」，才會填進那台裝置的 localStorage。

⚠️ 僅供 demo。正式環境不要跑，也請刪掉 web\\demo-persona.json。
清掉重來：sqlite3 data\\accounts.db "DELETE FROM accounts WHERE role='member'"
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Windows 主控台預設 cp950，印中文與 ✅ 會直接炸掉
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aidstation import auth, members  # noqa: E402
from aidstation.schemas import MatchingProfile  # noqa: E402

PERSONA_FILE = ROOT / "web" / "demo-persona.json"
DEFAULT_PASSWORD = "demo1234"


def seed(persona: dict, password: str) -> None:
    account = persona["account"]
    profile = persona.get("matching_profile") or {}

    # 同一個防線：媒合資料若混進 PrivateFormProfile 欄位，這裡就會炸，
    # 不會等到示範當天才發現個資被寫進資料庫。
    MatchingProfile.model_validate(profile)

    if auth.get_account(account) is None:
        auth.create_account(account, password, auth.ROLE_MEMBER)
        action = "建立"
    else:
        with auth._connect() as conn:
            conn.execute("UPDATE accounts SET password_hash = ?, role = ? WHERE username = ?",
                         (auth.hash_password(password), auth.ROLE_MEMBER, account))
        action = "更新"

    members.save_member(account, profile)
    print(f"✅ {action}帳號「{account}」（{persona.get('label', '')}）")
    print(f"   密碼：{password}")
    print(f"   媒合資料：{'、'.join(f'{k}={v}' for k, v in profile.items())}")


if __name__ == "__main__":
    if not PERSONA_FILE.exists():
        sys.exit(f"❌ 找不到 {PERSONA_FILE}，沒有可以建立的示範農民。")
    password = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PASSWORD
    if len(password) < auth.MIN_PASSWORD:
        sys.exit(f"❌ 密碼至少要 {auth.MIN_PASSWORD} 個字。")

    personas = json.loads(PERSONA_FILE.read_text(encoding="utf-8")).get("personas", [])
    for persona in personas:
        seed(persona, password)

    print()
    print("接下來：")
    print("  1. 啟動 API 後開 http://127.0.0.1:8000/app/login.html 用上面的帳密登入")
    print("  2. 在「我的資料」頁按「載入示範資料」把個人資料填進這台裝置")
    print("  3. 「這次發生的事」選天災與損失成數，就會媒合到天然災害現金救助")
    print("  4. 從推薦卡進官方表單準備頁，受災證明書就是填好的")
