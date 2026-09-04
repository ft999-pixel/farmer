"""白話指南：給農民讀的說明文章，內容由後台維護。

Markdown 支援標題、粗體、清單、連結，但**不支援原始 HTML**。
作法是「先把全文跳脫，再套用已知語法」——跳脫之後 <script> 只會變成畫面上的
文字，永遠不可能被瀏覽器執行。這樣就不需要外掛 Markdown 套件，也沒有它們
夾帶原始 HTML 的風險。

ponytail: 自製 Markdown 子集而非裝套件，因為只需要 5 種語法且安全性要自己掌握。
          需要表格、圖片、程式碼區塊時再換 markdown-it-py 並開啟 HTML 過濾。
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from .fields import DATA_DIR

STORE = DATA_DIR / "guides.json"

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SAFE_URL = re.compile(r"^(https?://|/)")


def _inline(text: str) -> str:
    """處理行內語法。傳進來的 text 必須已經跳脫過。"""
    text = _BOLD.sub(r"<strong>\1</strong>", text)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        # 只放行 http(s) 與站內路徑，擋掉 javascript: 這類會執行程式的網址
        if not _SAFE_URL.match(url):
            return label
        safe = url.replace('"', "%22")
        rel = ' target="_blank" rel="noopener noreferrer"' if url.startswith("http") else ""
        return f'<a href="{safe}"{rel}>{label}</a>'

    return _LINK.sub(link, text)


def render_markdown(text: str) -> str:
    """Markdown 子集 → HTML。支援 # 標題、**粗體**、- 清單、1. 編號、[文字](網址)。"""
    out: list[str] = []
    list_tag: str | None = None
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + "<br>".join(para) + "</p>")
            para.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for raw in (text or "").splitlines():
        line = html.escape(raw.strip(), quote=False)   # 先跳脫：原始 HTML 從此只是文字
        if not line:
            flush_para()
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            flush_para()
            close_list()
            level = min(len(heading.group(1)) + 1, 4)   # # → h2，避免蓋過頁面主標題
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        number = re.match(r"^\d+[.)]\s+(.*)$", line)
        if bullet or number:
            flush_para()
            want = "ul" if bullet else "ol"
            if list_tag != want:
                close_list()
                out.append(f"<{want}>")
                list_tag = want
            out.append(f"<li>{_inline((bullet or number).group(1))}</li>")
            continue
        close_list()
        para.append(_inline(line))
    flush_para()
    close_list()
    return "\n".join(out)


# ---- 資料存取 ------------------------------------------------------------

def _path() -> Path:
    import os
    return Path(os.environ.get("AIDSTATION_GUIDES") or STORE)


def load_guides() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_guides(guides: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(guides, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def get_guide(guide_id: str) -> dict | None:
    return next((g for g in load_guides() if g.get("id") == guide_id), None)


def validate_guide(guide: dict) -> list[str]:
    errors = []
    if not (guide.get("id") or "").strip():
        errors.append("缺少代號")
    elif not re.match(r"^[a-z0-9][a-z0-9-]{1,63}$", guide["id"]):
        errors.append("代號只能用小寫英文、數字與連字號，例如 disaster-72hr")
    if not (guide.get("title") or "").strip():
        errors.append("缺少標題")
    if not (guide.get("body") or "").strip():
        errors.append("內文不能空白")
    return errors


def upsert_guide(guide: dict) -> dict:
    """新增或更新。維持既有順序，新的排在最後。"""
    guides = load_guides()
    guide = {**guide, "updated_at": date.today().isoformat()}
    for i, g in enumerate(guides):
        if g.get("id") == guide["id"]:
            guides[i] = {**g, **guide}
            break
    else:
        guides.append(guide)
    save_guides(guides)
    return guide


def delete_guide(guide_id: str) -> bool:
    guides = load_guides()
    kept = [g for g in guides if g.get("id") != guide_id]
    if len(kept) == len(guides):
        return False
    save_guides(kept)
    return True
