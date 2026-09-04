"""一鍵啟動：python run.py

自動把 src 加入模組路徑，不需要設 PYTHONPATH（cmd 和 PowerShell 都適用）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# Windows 預設 cp950 編不出 emoji／部分中文，輸出轉 UTF-8（PowerShell 導向檔案時尤其會炸）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn


def lan_ip() -> str | None:
    """查出這台電腦在區域網路的 IP，好讓隊友連得進來。查不到就回 None。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))     # 不會真的送出封包，只是問作業系統走哪張網卡
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # 預設只有自己這台看得到。要給同一個網路的隊友看：set HOST=0.0.0.0
    host = os.environ.get("HOST", "127.0.0.1")
    # 自動重啟預設關閉。要開請先 pip install watchfiles，再用 RELOAD=1 啟動；
    # 沒裝 watchfiles 時 uvicorn 會退回 StatReload，在 Windows 上會偵測到變更卻重啟不完全
    # （舊的程式碼繼續服務，看起來像沒改到）——寧可不開，也不要給你一個假的自動重啟。
    reload = os.environ.get("RELOAD") == "1"
    print(f"🌾 農民補給站啟動中…")
    print(f"   你自己看：  http://127.0.0.1:{port}/app/")
    if host == "0.0.0.0":
        ip = lan_ip()
        if ip:
            print(f"   隊友看這個：http://{ip}:{port}/app/   ← 把這行貼給隊友"
                  f"（要跟你連同一個 Wi-Fi）")
        else:
            print("   ⚠️ 查不到區域網路 IP，可能沒連上網路。")
        print("   ⚠️ 已對外開放：確認 .env 的 ADMIN_PASSWORD 不是預設值再繼續。")
    print("   改完 .py 要按 Ctrl+C 再重跑一次；改 html/js/css 只要重新整理瀏覽器。")
    uvicorn.run("aidstation.api:app", host=host, port=port, reload=reload)
