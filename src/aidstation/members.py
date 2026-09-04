"""會員資料（Demo 版）：存農民的基本資料，換裝置也看得到。

資料庫用 stdlib 的 sqlite3——這個規模（示範用、幾十筆）不需要 Postgres，
也不必為此多裝一個套件。要換 Postgres 時只需改本檔的 _connect 與四個 SQL。

ponytail: 身分用「農民自己取的代號」，不是真的登入。Demo 用，別人猜到代號就能看到那筆資料。
          要真的保護個資，改接 LINE Login（拿 LINE userId 當 line_id），本檔其餘不用動。

存什麼：作物、鄉鎮、土地權屬等媒合條件，加上姓名／電話／地址（列印申請表用）。
不存什麼：身分證字號、銀行帳號——刻意不收，農民到現場親手寫。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from .fields import DATA_DIR

router = APIRouter(prefix="/members", tags=["members"])

DB_PATH = DATA_DIR / "members.db"
COOKIE = "aidstation_member"
SESSION_DAYS = 30
_CODE_OK = re.compile(r"^[\w一-鿿-]{2,32}$")   # 中英數字與連字號，2～32 字

_SECRET = (os.environ.get("MEMBER_SECRET") or secrets.token_hex(32)).encode()


def _db_path() -> Path:
    return Path(os.environ.get("AIDSTATION_MEMBERS_DB") or DB_PATH)


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # facts／contact 直接存 JSON 字串：fields.json 增減欄位時不用改資料庫結構
    conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            code       TEXT PRIMARY KEY,
            contact    TEXT NOT NULL DEFAULT '{}',
            facts      TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
    return conn


# ---- 簽章 cookie（把代號綁進簽章，避免隨手改 cookie 就變成別人）------------

def _sign(code: str, expires: int) -> str:
    # cookie 只能放 latin-1，中文代號（阿明伯）直接塞會炸——轉成十六進位再放
    tag = code.encode("utf-8").hex()
    mac = hmac.new(_SECRET, f"{tag}|{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{tag}|{expires}|{mac}"


def _code_from_token(token: str | None) -> str | None:
    if not token or token.count("|") != 2:
        return None
    tag, expires, _mac = token.split("|")
    try:
        if int(expires) < time.time():
            return None
        code = bytes.fromhex(tag).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return code if hmac.compare_digest(token, _sign(code, int(expires))) else None


def require_member(token: str | None) -> str:
    code = _code_from_token(token)
    if code is None:
        raise HTTPException(401, "請先輸入你的代號")
    return code


# ---- 資料存取 ------------------------------------------------------------

def get_member(code: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM members WHERE code = ?", (code,)).fetchone()
    if row is None:
        return None
    return {"code": row["code"], "contact": json.loads(row["contact"]),
            "facts": json.loads(row["facts"]), "updated_at": row["updated_at"]}


def save_member(code: str, contact: dict, facts: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("""
            INSERT INTO members (code, contact, facts, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                contact = excluded.contact,
                facts = excluded.facts,
                updated_at = excluded.updated_at
        """, (code, json.dumps(contact, ensure_ascii=False),
              json.dumps(facts, ensure_ascii=False), now, now))
    return get_member(code)


def delete_member(code: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM members WHERE code = ?", (code,))
    return cur.rowcount > 0


# ---- API ----------------------------------------------------------------

class LoginRequest(BaseModel):
    code: str


class SaveRequest(BaseModel):
    contact: dict = {}
    facts: dict = {}


@router.post("/login")
def login(req: LoginRequest, response: Response) -> dict:
    """輸入代號即登入；沒有這個代號就當場建一個。Demo 版沒有密碼。"""
    code = (req.code or "").strip()
    if not _CODE_OK.match(code):
        raise HTTPException(422, "代號請用 2～32 個中英文字、數字或連字號，例如「阿明伯」")
    member = get_member(code)
    created = member is None
    if created:
        member = save_member(code, {}, {})
    token = _sign(code, int(time.time()) + SESSION_DAYS * 86400)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                        max_age=SESSION_DAYS * 86400)
    return {"created": created, **member}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def read_me(aidstation_member: str | None = Cookie(None)) -> dict:
    code = _code_from_token(aidstation_member)
    if code is None:
        return {"logged_in": False}
    member = get_member(code)
    if member is None:                     # 資料被刪掉了，cookie 卻還在
        return {"logged_in": False}
    return {"logged_in": True, **member}


@router.post("/me")
def update_me(req: SaveRequest, aidstation_member: str | None = Cookie(None)) -> dict:
    code = require_member(aidstation_member)
    return save_member(code, req.contact, req.facts)


@router.delete("/me")
def remove_me(response: Response, aidstation_member: str | None = Cookie(None)) -> dict:
    """農民要能刪掉自己的資料——存了個資就必須給得回去。"""
    code = require_member(aidstation_member)
    deleted = delete_member(code)
    response.delete_cookie(COOKIE)
    return {"deleted": deleted}
