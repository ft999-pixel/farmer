"""統一登入：由系統判斷身分與去處，不讓使用者自己選入口。

判斷方式是「憑證類型」，不是使用者勾選：

    有填密碼   → 以承辦人員驗證，成功後進後臺維護
    沒填密碼   → 以農民代號登入，進「我的資料」
    LINE 登入  → 一律是農民（見 line_login.py）

⚠️ 目前後臺是「一組共用密碼」，沒有個別帳號，所以無法依帳號分辨承辦人員個人。
   要做到「誰改了什麼」可追溯到人，需要真正的使用者表；
   在那之前，稽核紀錄只能記下動作，記不到是哪一位承辦。

獨立成一個檔案，不動 members.py／admin.py 的既有端點，
兩邊的登入方式維持原樣，這裡只是在前面加一層分派。
"""
from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from . import admin as admin_mod
from . import members as members_mod

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    identifier: str = ""        # 農民的代號，或承辦人員的帳號（目前僅作顯示用）
    password: str = ""          # 只有承辦人員需要


@router.post("/login")
def login(req: LoginRequest, response: Response) -> dict:
    identifier = (req.identifier or "").strip()
    password = req.password or ""

    # ---- 有密碼＝以承辦人員身分登入 ----
    if password:
        expected = admin_mod._password()
        if expected is None:
            raise HTTPException(503, "後臺尚未啟用：請在 .env 設定 ADMIN_PASSWORD。")
        if not hmac.compare_digest(password, expected):
            # 密碼錯就直接擋，不要默默改用農民身分登入——那會讓人不知道自己是誰
            raise HTTPException(401, "密碼不對。如果你是農民，密碼欄留空就好。")
        token = admin_mod._sign(int(time.time()) + admin_mod.SESSION_HOURS * 3600)
        response.set_cookie(admin_mod.COOKIE, token, httponly=True, samesite="strict",
                            max_age=admin_mod.SESSION_HOURS * 3600)
        return {"role": "admin", "redirect": "admin.html", "name": identifier or "承辦人員"}

    # ---- 沒有密碼＝農民 ----
    if not identifier:
        raise HTTPException(422, "請輸入你的代號。")
    if not members_mod._CODE_OK.match(identifier):
        raise HTTPException(422, "代號請用 2～32 個中英文字、數字或連字號，例如「阿明伯」。")

    created = members_mod.get_member(identifier) is None
    if created:
        members_mod.save_member(identifier, {})
    token = members_mod._sign(identifier, int(time.time()) + members_mod.SESSION_DAYS * 86400)
    response.set_cookie(members_mod.COOKIE, token, httponly=True, samesite="lax",
                        max_age=members_mod.SESSION_DAYS * 86400)
    return {"role": "member", "redirect": "profile.html", "name": identifier, "created": created}
