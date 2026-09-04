"""補助資料維護後台（機關端）。

設計重點——這裡改壞了，農民就會看到錯的補助資訊，所以：

1. **存檔前驗證**：與啟動載入共用 knowledge.validate_program()，
   後台存得進去的資料，重啟一定載得起來（不會因為一次誤存讓整站起不來）。
2. **先備份再覆寫**：舊檔留在 data/backups/，隨時可回滾。
3. **稽核軌跡**：誰在什麼時候改了哪一筆、改前改後，寫進 data/admin_audit.jsonl。
   （承辦不一定會用 Git，稽核不能只靠版本庫。）
4. **存檔即生效**：寫檔後重載記憶體中的補助清單與對話引擎快取。

登入採單一密碼（.env 的 ADMIN_PASSWORD），簽章 cookie 以 stdlib hmac 實作，
不額外裝套件。密碼沒設時後台整個關閉——不留無密碼的後門。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from . import guides
from .fields import DATA_DIR, load_fields
from .knowledge import OPERATORS, load_programs, validate_program

router = APIRouter(prefix="/admin", tags=["admin"])

PROGRAMS_DIR = DATA_DIR / "programs"
BACKUP_DIR = DATA_DIR / "backups"
AUDIT_LOG = DATA_DIR / "admin_audit.jsonl"

COOKIE = "aidstation_admin"
SESSION_HOURS = 8
_ID_OK = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")   # 檔名直接用 id，必須擋住路徑穿越

# 簽章金鑰：優先用 .env 設定，沒設就每次啟動隨機產生（重啟後需重新登入）
_SECRET = (os.environ.get("ADMIN_SECRET") or secrets.token_hex(32)).encode()


def _password() -> str | None:
    pw = os.environ.get("ADMIN_PASSWORD")
    return pw if pw else None


def _sign(expires: int) -> str:
    mac = hmac.new(_SECRET, str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{mac}"


def _valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires, _, _mac = token.partition(".")
    try:
        if int(expires) < time.time():
            return False
    except ValueError:
        return False
    return hmac.compare_digest(token, _sign(int(expires)))


def require_login(session: str | None) -> None:
    if _password() is None:
        raise HTTPException(503, "後台未啟用：請在 .env 設定 ADMIN_PASSWORD 後重新啟動。")
    if not _valid_token(session):
        raise HTTPException(401, "請先登入")


def _find_path(program_id: str) -> Path | None:
    """依 id 找出實際檔案。檔名不一定等於 id（既有資料就是如此），
    所以必須讀內容比對——否則存檔會另開一個新檔，變成兩筆同 id。"""
    for path in sorted(PROGRAMS_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                if json.load(f).get("id") == program_id:
                    return path
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _program_path(program_id: str) -> Path:
    """回傳既有檔案路徑；不存在則給新檔的預定路徑（以 id 命名）。"""
    if not _ID_OK.match(program_id or ""):
        raise HTTPException(422, "補助代號只能用小寫英數字與連字號（3～64 字），例如 moa-disaster-cash")
    return _find_path(program_id) or (PROGRAMS_DIR / f"{program_id}.json")


def _audit(action: str, program_id: str, before: Any, after: Any) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "at": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "program_id": program_id,
            "before": before,
            "after": after,
        }, ensure_ascii=False) + "\n")


def _backup(path: Path) -> str | None:
    """覆寫或刪除前先備份，回傳備份檔名。"""
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"{path.stem}.{stamp}.json"
    shutil.copy2(path, dest)
    return dest.name


def reload_runtime() -> int:
    """存檔即生效：重載記憶體中的補助清單，並清掉對話引擎的快取。

    api 與 line_webhook 各自持有 Flow／PROGRAMS，這裡一起失效，
    否則農民端還是會拿到舊資料。晚匯入避免與 api 互相 import。
    """
    from . import api, line_webhook
    api.PROGRAMS = load_programs(fields=api.FIELDS)
    api._web_flow = None
    line_webhook._flow = None
    return len(api.PROGRAMS)


# ---- 登入 ---------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(req: LoginRequest, response: Response) -> dict:
    expected = _password()
    if expected is None:
        raise HTTPException(503, "後台未啟用：請在 .env 設定 ADMIN_PASSWORD 後重新啟動。")
    if not hmac.compare_digest(req.password, expected):
        raise HTTPException(401, "密碼不對")
    token = _sign(int(time.time()) + SESSION_HOURS * 3600)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                        max_age=SESSION_HOURS * 3600)
    return {"ok": True, "hours": SESSION_HOURS}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/session")
def session_state(aidstation_admin: str | None = Cookie(None)) -> dict:
    return {"enabled": _password() is not None,
            "logged_in": _valid_token(aidstation_admin)}


# ---- 表單建構器需要的字典 ------------------------------------------------

@router.get("/schema")
def get_schema(aidstation_admin: str | None = Cookie(None)) -> dict:
    """條件建構器的下拉選單來源：欄位字典＋可用運算子。"""
    require_login(aidstation_admin)
    fields = load_fields()
    return {
        "fields": {k: {"label": v.get("label", k), "type": v.get("type"),
                       "values": v.get("values")} for k, v in fields.items()},
        "operators": list(OPERATORS),
        "categories": sorted({p.get("category") for p in load_programs(fields=fields)
                              if p.get("category")}),
    }


# ---- 補助 CRUD ----------------------------------------------------------

@router.get("/programs")
def list_programs(aidstation_admin: str | None = Cookie(None)) -> list[dict]:
    require_login(aidstation_admin)
    out = []
    for path in sorted(PROGRAMS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        src = p.get("source") or {}
        out.append({"id": p.get("id"), "name": p.get("name"),
                    "category": p.get("category"),
                    "status": src.get("status"),
                    "last_verified": src.get("last_verified"),
                    "stale": _is_stale(src.get("last_verified")),
                    "file": path.name})
    return out


def _is_stale(last_verified: str | None, months: int = 6) -> bool:
    """超過半年沒覆核就標記——資料過期沒人發現，是這套系統最大的風險。"""
    if not last_verified:
        return True
    try:
        d = date.fromisoformat(last_verified)
    except ValueError:
        return True
    return (date.today() - d).days > months * 30


@router.get("/program/{program_id}")
def get_program(program_id: str, aidstation_admin: str | None = Cookie(None)) -> dict:
    require_login(aidstation_admin)
    path = _program_path(program_id)
    if not path.exists():
        raise HTTPException(404, "找不到這筆補助")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class SaveRequest(BaseModel):
    program: dict


@router.post("/program/{program_id}")
def save_program(program_id: str, req: SaveRequest,
                 aidstation_admin: str | None = Cookie(None)) -> dict:
    """驗證 → 備份 → 寫檔 → 稽核 → 重載。任一步失敗就不動檔案。"""
    require_login(aidstation_admin)
    path = _program_path(program_id)
    program = req.program
    if program.get("id") != program_id:
        raise HTTPException(422, f"資料裡的 id「{program.get('id')}」與網址的「{program_id}」不一致")

    errors = validate_program(program, load_fields())
    if errors:
        raise HTTPException(422, {"message": "資料有問題，沒有存檔", "errors": errors})

    before = None
    if path.exists():
        with open(path, encoding="utf-8") as f:
            before = json.load(f)
    backup = _backup(path)

    PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(program, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    try:
        count = reload_runtime()
    except ValueError as exc:      # 理論上驗證已擋掉；真的發生就把檔案還原
        if before is not None:
            path.write_text(json.dumps(before, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        reload_runtime()
        raise HTTPException(500, f"存檔後重載失敗，已還原：{exc}")

    _audit("update" if before else "create", program_id, before, program)
    return {"ok": True, "created": before is None, "backup": backup,
            "programs_loaded": count}


@router.delete("/program/{program_id}")
def delete_program(program_id: str, aidstation_admin: str | None = Cookie(None)) -> dict:
    require_login(aidstation_admin)
    path = _program_path(program_id)
    if not path.exists():
        raise HTTPException(404, "找不到這筆補助")
    with open(path, encoding="utf-8") as f:
        before = json.load(f)
    backup = _backup(path)
    path.unlink()
    _audit("delete", program_id, before, None)
    return {"ok": True, "backup": backup, "programs_loaded": reload_runtime()}


# ---- 白話指南 ------------------------------------------------------------

class GuideRequest(BaseModel):
    guide: dict


@router.get("/guides")
def admin_list_guides(aidstation_admin: str | None = Cookie(None)) -> list[dict]:
    require_login(aidstation_admin)
    return guides.load_guides()


@router.post("/guide/{guide_id}")
def admin_save_guide(guide_id: str, req: GuideRequest,
                     aidstation_admin: str | None = Cookie(None)) -> dict:
    require_login(aidstation_admin)
    guide = {**req.guide, "id": guide_id}
    errors = guides.validate_guide(guide)
    if errors:
        raise HTTPException(422, {"message": "指南有問題，沒有存檔", "errors": errors})
    existed = guides.get_guide(guide_id) is not None
    saved = guides.upsert_guide(guide)
    _audit("update" if existed else "create", f"guide:{guide_id}", None, saved)
    return {"ok": True, "created": not existed, "guide": saved}


class PreviewRequest(BaseModel):
    body: str = ""


@router.post("/guide-preview")
def admin_preview_guide(req: PreviewRequest,
                        aidstation_admin: str | None = Cookie(None)) -> dict:
    """後台預覽用同一支渲染器，所見即農民所得。"""
    require_login(aidstation_admin)
    return {"html": guides.render_markdown(req.body)}


@router.delete("/guide/{guide_id}")
def admin_delete_guide(guide_id: str,
                       aidstation_admin: str | None = Cookie(None)) -> dict:
    require_login(aidstation_admin)
    before = guides.get_guide(guide_id)
    if not guides.delete_guide(guide_id):
        raise HTTPException(404, "找不到這篇指南")
    _audit("delete", f"guide:{guide_id}", before, None)
    return {"ok": True}


@router.get("/audit")
def get_audit(limit: int = 50, aidstation_admin: str | None = Cookie(None)) -> list[dict]:
    """異動紀錄（最新在前）。只回傳摘要，完整前後值留在檔案裡。"""
    require_login(aidstation_admin)
    if not AUDIT_LOG.exists():
        return []
    rows = []
    for line in AUDIT_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({"at": r.get("at"), "action": r.get("action"),
                     "program_id": r.get("program_id"),
                     "name": (r.get("after") or r.get("before") or {}).get("name")})
    return rows[::-1][:max(1, min(limit, 500))]
