"""產生示範卡點資料，讓儀表板有東西可看：python scripts\\seed_blockers.py

⚠️ 僅供 demo／版面確認。正式環境不要跑（會污染真實統計）。
清空重來：刪掉 data\\blockers.jsonl。
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aidstation import blockers  # noqa: E402

CATEGORIES = ["災害救助", "農民福利", "農業保險", "平時申報"]
TOWNSHIPS = ["玉井區", "楠西區", "南化區", "大內區", "左鎮區", "山上區"]
# (原因, 來源, 權重) — 權重刻意不均，才看得出排行與交叉的差異
MIX = [
    ("缺件補正", blockers.SOURCE_DOC, 30),
    ("資格不符", blockers.SOURCE_DOC, 22),
    ("超過申請期限", blockers.SOURCE_DOC, 16),
    ("文件生不出來", blockers.SOURCE_STUCK, 20),
    ("看不懂", blockers.SOURCE_STUCK, 15),
    ("太麻煩了", blockers.SOURCE_STUCK, 12),
    ("金額核減", blockers.SOURCE_DOC, 8),
    ("查核未過", blockers.SOURCE_DOC, 6),
]

if __name__ == "__main__":
    if blockers.STORE.exists():
        print(f"⚠️ {blockers.STORE} 已存在，示範資料會疊加上去。")
    random.seed(20260904)
    today = date.today()
    reasons = [r for r, _, _ in MIX]
    weights = [w for _, _, w in MIX]
    sources = {r: s for r, s, _ in MIX}
    n = 0
    for days_ago in range(56):
        d = today - timedelta(days=days_ago)
        # 越接近今天量越多；「超過申請期限」在假想截止日（14 天前）附近加倍
        for _ in range(random.randint(1, 5)):
            reason = random.choices(reasons, weights)[0]
            if reason == "超過申請期限" and not (10 <= days_ago <= 20) and random.random() < 0.6:
                continue
            # 地方公所多半卡在缺件與查核，中央多半卡在資格與金額——刻意做出差異
            weight_local = {"缺件補正": .75, "查核未過": .8, "太麻煩了": .7,
                            "資格不符": .3, "金額核減": .25}.get(reason, .5)
            level = blockers.LEVEL_LOCAL if random.random() < weight_local else blockers.LEVEL_CENTRAL
            blockers.record(reason, sources[reason],
                            category=random.choice(CATEGORIES),
                            township=random.choice(TOWNSHIPS), level=level, on=d)
            n += 1
    print(f"✅ 已寫入 {n} 筆示範卡點 → {blockers.STORE}")
    print("   開 http://127.0.0.1:8000/app/dashboard.html 看儀表板")
