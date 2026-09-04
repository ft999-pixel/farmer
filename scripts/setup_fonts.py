# -*- coding: utf-8 -*-
"""下載源泉圓體並轉成網頁用 woff2（只需執行一次）。

用法（在專案根目錄）：
    pip install fonttools brotli
    python scripts\\setup_fonts.py

來源一（官方）：ButTaiwan GitHub v2.100 OTF
來源二（備用）：ziti.net.cn TTC 載點（v1，含 MD5 驗證，自動挑出 TW 版）

完成後 web/fonts/ 會有：
    GenSenRounded2TW-H.woff2   標題（Heavy）
    GenSenRounded2TW-M.woff2   按鈕（Medium）
    GenSenRounded2TW-R.woff2   內文（Regular）
"""
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

GITHUB_ZIP = "https://github.com/ButTaiwan/gensen-font/releases/download/v2.100/GenSenRounded2TW-otf.zip"

# 備用載點（ziti.net.cn 頁面公布的直接連結與 MD5）
FALLBACK = {
    "H": ("https://www.ziti.net.cn/static/upload/other/20210904/1630746819480794.ttc",
          "16fa20e249d3c542236cf8196542d98e"),
    "B": ("https://www.ziti.net.cn/static/upload/other/20210904/1630746818669051.ttc",
          "7dd86fee9387c38e15b4c7c6952c680d"),
    "M": ("https://www.ziti.net.cn/static/upload/other/20210904/1630746819666812.ttc",
          "1ea35c36fe08a9bc3f86096259942e01"),
    "R": ("https://www.ziti.net.cn/static/upload/other/20210904/1630746819834028.ttc",
          "67a29e0ec3b17ae5fc4d7f6e0dded74a"),
}

WEIGHTS = ["H", "B", "M", "R"]
OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "fonts"


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=120).read()


def save_woff2(font, weight: str) -> None:
    font.flavor = "woff2"
    out_path = OUT_DIR / f"GenSenRounded2TW-{weight}.woff2"
    font.save(str(out_path))
    print(f"✓ {out_path.name}（{out_path.stat().st_size // 1024} KB）")


def pick_tw_face(ttc_bytes: bytes, TTFont, TTCollection):
    """TTC 合集裡挑出 TW 版；挑不到就退回第一個。"""
    coll = TTCollection(io.BytesIO(ttc_bytes))
    for font in coll.fonts:
        name = font["name"].getDebugName(1) or ""
        if "TW" in name:
            return font
    return coll.fonts[0]


def try_github(TTFont) -> bool:
    try:
        print("嘗試官方 GitHub 下載（約 20MB）…")
        data = download(GITHUB_ZIP)
    except Exception as err:
        print(f"官方載點失敗（{err}），改用備用載點。")
        return False
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        for weight in WEIGHTS:
            match = [n for n in names if n.endswith(f"-{weight}.otf")]
            if not match:
                print(f"⚠ 官方包裡找不到字重 {weight}")
                return False
            save_woff2(TTFont(io.BytesIO(zf.read(match[0]))), weight)
    return True


def try_fallback(TTFont, TTCollection) -> None:
    for weight in WEIGHTS:
        url, md5_expected = FALLBACK[weight]
        print(f"下載 {weight}（約 15MB）…")
        data = download(url)
        md5_actual = hashlib.md5(data).hexdigest()
        if md5_actual != md5_expected:
            print(f"✗ 字重 {weight} MD5 不符（{md5_actual}），檔案可能有問題，略過。")
            continue
        save_woff2(pick_tw_face(data, TTFont, TTCollection), weight)


def main() -> None:
    try:
        from fontTools.ttLib import TTCollection, TTFont  # noqa: WPS433
    except ImportError:
        print("請先安裝轉檔工具：pip install fonttools brotli")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not try_github(TTFont):
        try_fallback(TTFont, TTCollection)

    done = [p.name for p in OUT_DIR.glob("*.woff2")]
    if len(done) == 3:
        print("完成！重新整理網頁（Ctrl+F5）就會看到源泉圓體。")
    else:
        print(f"目前完成：{done}。缺的字重請再跑一次，或把網路問題貼給 Claude。")


if __name__ == "__main__":
    main()
