"""手動驗證：合成一張假公文照片，跑完整的「拍照 → 白話卡」流程。

用法（需要 ANTHROPIC_API_KEY）：
    set PYTHONPATH=src && python scripts/try_doc_photo.py

不是 pytest 測試——它會真的呼叫 Claude vision，要花錢。
"""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

LINES = [
    "臺南市玉井區公所　函",
    "",
    "發文日期：中華民國115年8月20日",
    "發文字號：南玉農字第1150008888號",
    "",
    "主旨：台端申請115年颱風農業天然災害現金救助，",
    "　　　所附資料不全，請補正，請查照。",
    "",
    "說明：",
    "一、依農業天然災害救助辦法第10條規定辦理。",
    "二、請檢具土地登記謄本影本1份、農保被保險人",
    "　　證明1份，於文到7日內送本所農業課補正。",
    "三、逾期未補正者，將駁回本件申請，不予救助。",
    "",
    "承辦人：農業課　電話：06-5741141轉123",
]


def make_image(path: Path) -> None:
    img = Image.new("RGB", (1000, 720), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 26)
    for i, line in enumerate(LINES):
        draw.text((60, 40 + i * 38), line, fill="black", font=font)
    img.save(path, quality=88)


def main() -> None:
    out = Path(__file__).parent / "_doc_sample.jpg"
    make_image(out)
    print(f"合成公文照片：{out}（{out.stat().st_size} bytes）\n")

    from fastapi.testclient import TestClient
    from aidstation.api import app

    b64 = base64.b64encode(out.read_bytes()).decode()
    client = TestClient(app)
    resp = client.post("/translate", json={
        "image": f"data:image/jpeg;base64,{b64}",
        "received_date": "2026-09-01",
        "today": "2026-09-04",
    })
    print("HTTP", resp.status_code)
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
