# 農民補給站（核心引擎）

說一句話找到你該領的補助，拍一張照看懂看不懂的公文。
本 repo 目前為 **核心引擎＋知識庫**（MVP P0 第一塊），設計依據見《系統設計建議書.md》。

## 架構原則

- **LLM 不做資格判定**：判定只發生在規則引擎（三值邏輯：符合／可能符合／不符合），每條結果附法條依據。
- **新增補助不改程式**：補助以 JSON 掛載於 `data/programs/`，條件欄位須先註冊於 `data/fields.json`（欄位字典是系統中樞）。
- **期限兩型分流**：公告型直接倒數；文到型必須先問「你哪一天收到的？」再推算，並顯示計算式。解析不出就導向承辦電話，絕不猜。

## 目錄

```
src/aidstation/
  fields.py        欄位字典載入與正規化（含台語別名：檨仔→芒果）
  engine.py        三值邏輯規則引擎＋缺口驅動提問（期限急迫者優先問）
  deadline.py      期限兩型分流（工作日接假日行事曆）
  knowledge.py     知識庫載入與啟動時驗證
  extract.py       語意抽取層：Claude 受控輸出＋validate_facts 幻覺防火牆＋關鍵字後備
  document.py      公文白話化：受控欄位、民國日期解析、白話卡、收文日反問
  flow.py          對話狀態機（LINE／PWA 共用）：一次一題、我卡住了、公文流程
  line_webhook.py  LINE Webhook：簽章驗證、quick reply、dry-run 測試模式
  api.py           FastAPI（/match /translate /fields /programs /deadline /line/webhook）
data/
  fields.json   欄位字典
  holidays.json 國定假日（上線前須換完整行事曆）
  programs/     補助種子資料（目前 5 項，均標示 sample）
scripts/demo.py 終端機互動展示
tests/          pytest（30 項）
```

## 環境變數

| 變數 | 用途 | 未設定時 |
|------|------|---------|
| `ANTHROPIC_API_KEY` | 語意抽取與公文翻譯走 Claude | 降級為關鍵字／規則式（離線可跑） |
| `ANTHROPIC_MODEL` | 指定模型 | claude-opus-4-8 |
| `LINE_CHANNEL_SECRET` | Webhook 簽章驗證 | 跳過驗證（僅限開發） |
| `LINE_CHANNEL_ACCESS_TOKEN` | 回覆訊息 | dry-run：回覆放在 HTTP 回應中 |

安全設計：LLM 輸出一律經過 `validate_facts()`／`sanitize_doc()` 過濾，
未註冊欄位與不合法值直接丟棄——LLM 永遠無法影響資格判定，只能提供欄位值。
LLM 故障時自動降級為規則式路徑，服務不中斷。

## 快速開始

```bash
pip install -r requirements.txt
python -m pytest tests/ -q          # 跑測試
PYTHONPATH=src python scripts/demo.py   # 終端機互動 demo
PYTHONPATH=src uvicorn aidstation.api:app --reload  # 啟動 API
```

## API 範例

```bash
curl -X POST localhost:8000/match -H 'content-type: application/json' \
  -d '{"facts": {"crop": "檨仔", "event": "天然災害", "township": "玉井區", "loss_rate": 0.6, "land_tenure": "口頭租約"}}'
```

回傳：各補助的三級結果、未確認欄位、下一個該問的問題、應備文件（含豁免標記）、期限倒數。

## 下一步（依 MVP 切分）

1. ~~LLM 受控輸出抽取層~~ ✅（extract.py，含降級路徑）
2. 公文白話化 ✅（document.py）；**OCR 接入待辦**（PaddleOCR 台灣公文微調）
3. LINE 接入 ✅（line_webhook.py）；**待辦**：建立官方帳號、設定 Rich Menu 三大鍵、
   影像下載→OCR 串接、語音下載→台語 ASR（Breeze-ASR）串接
4. 協辦者 PWA 工作台（案件列表＋A4 摘要匯出）
5. 真實公告資料匯入與人工覆核流程
6. 卡點回報落庫（flow.py 的 `_handle_stuck` 已留落點）

⚠️ `data/programs/` 目前全為示範資料（source.status = "sample"），不可用於真實申辦指引。

## 子模組

- `module/prefill/`：預填表單服務（Flask，獨立 SQLite，預設 port 5000）。啟動與 API 見該目錄的 README。
