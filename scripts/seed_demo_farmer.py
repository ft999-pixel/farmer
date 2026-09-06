"""建立示範農民帳號：python scripts\\seed_demo_farmer.py [密碼]

讀 web\\demo-persona.json，把裡面的每個 persona 建成一個可登入的農民帳號，
並把 matching_profile 存進會員資料。密碼預設 demo1234，可用參數覆蓋。
重複執行沒關係：帳號已存在就只更新密碼與媒合資料。

部署站不必跑這支——設環境變數 DEMO_PASSWORD，API 啟動時會自動建（見
src/aidstation/demo_seed.py）。這支是給本機用的，順手把預設密碼填好。

private_form_profile（姓名、身分證、住址、電話、銀行帳號、地號）**不會**寫進
任何資料庫——那是 PrivateFormProfile，只能留在瀏覽器。示範時登入後到
「我的資料」頁按「載入示範資料」，才會填進那台裝置的 localStorage。

⚠️ 僅供 demo。正式環境不要跑，也請刪掉 web\\demo-persona.json。
清掉重來：sqlite3 data\\accounts.db "DELETE FROM accounts WHERE role='member'"
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Windows 主控台預設 cp950，印中文與 ✅ 會直接炸掉
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aidstation import auth  # noqa: E402
from aidstation.demo_seed import PERSONA_FILE, load_personas, seed_persona  # noqa: E402

DEFAULT_PASSWORD = "demo1234"

if __name__ == "__main__":
    personas = load_personas()
    if not personas:
        sys.exit(f"❌ {PERSONA_FILE} 沒有可用的示範農民。")

    password = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PASSWORD
    if len(password) < auth.MIN_PASSWORD:
        sys.exit(f"❌ 密碼至少要 {auth.MIN_PASSWORD} 個字。")

    for persona in personas:
        action = seed_persona(persona, password)
        profile = persona.get("matching_profile") or {}
        print(f"✅ {action}帳號「{persona['account']}」（{persona.get('label', '')}）")
        print(f"   密碼：{password}")
        print("   媒合資料：" + "、".join(f"{k}={v}" for k, v in profile.items()))

    print()
    print("接下來：")
    print("  1. python run.py 後開 http://127.0.0.1:8000/app/login.html 用上面的帳密登入")
    print("  2. 在「我的資料」頁按「載入示範資料」把個人資料填進這台裝置")
    print("  3. 「這次發生的事」選天災與損失成數，就會媒合到天然災害現金救助")
    print("  4. 從推薦卡或補助詳情頁「開始申請」，受災證明書就是填好的")
