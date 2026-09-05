# Futuremode Hero Demo

這是 Demo-first 的農民補助媒合流程：

自然語言找補助 → 一次補問 → 推薦與理由 → task checklist → 瀏覽器本地預填 → Preview / Print。

## 啟動

在 repo 根目錄執行：

```bash
DEMO_MODE=true DEMO_DATE=2026-08-20 venv/bin/python run.py
```

開啟 <http://127.0.0.1:8000/app/?demo=1>。

`DEMO_DATE=2026-08-20` 是交接資料指定的 Hero 日期；它讓 115 年省工農機與青年農民資料在舞台 demo 時保持可展示。正式日期未設定時，API 會使用系統日期並依 application round 判斷 `CLOSED`。

## Hero persona

在首頁輸入：

> 我去年才回來屏東種香蕉，大概八分地，有 QR Code，最近想買電動割草機。

預期流程：

1. 系統抽出概略所在地、作物、面積、從農年資、QR Code 與設備需求。
2. 只補問一題：割草機是否已有公告補助牌型/品牌型號。
3. 選擇「已在公告補助牌型」後，看到省工農業機械等推薦卡。
4. 卡片顯示 why、仍需確認的資訊、受理期限、承辦單位與下一步。
5. 按「開始申請」查看依期限/依賴排序的 task checklist。
6. 進入官方農機申請表，使用本機資料預填，修改後按 Preview / Print。

## 官方表單

預填 demo 使用 `futuremode_official_forms_v2/` 提供的農糧署官方 115 年計畫抽頁與 mapping，不自行重畫政府表單。主要 Hero 表單是：

- `farm_machine_115.labor_saving`：附表 9，官方 PDF 第 36 頁。
- `farm_machine_115.electric_replacement`：附表 16，官方 PDF 第 43 頁。

沒有官方紙本表單的計畫仍可出現在媒合結果，但會顯示線上申辦/尚未匯入，不會產生假的申請書。

## Privacy 驗收

- `MatchingProfile` 只含媒合所需的概略資料，可送 `POST /match`。
- `PrivateFormProfile`（姓名、身分證、電話、完整地址、銀行帳號、地號、簽名等）只存在 browser local storage。
- 重新整理表單頁後，local private fields 仍可還原。
- 開啟瀏覽器 Network 檢查 `/match`、會員 API 與表單 metadata request，payload 不應含 private-only 欄位。
- 預填產出的 PDF 是本機組合與列印；送件由農民自行完成。

## Smoke tests

```bash
venv/bin/python -m pytest -q
venv/bin/python -m py_compile src/aidstation/*.py
```

手動 smoke：

1. 用上述 persona 完成一次補問並看到推薦。
2. 在表單頁輸入任意假姓名、電話、身分證與地址（不要用真實資料），刷新後確認仍由本機還原。
3. 清空一個欄位，確認空白仍留在本機編輯區；填回後可 Preview / Print（空白欄位也可留待現場手寫確認）。
4. 貼上既有公文 smoke text，確認仍可翻成白話並計算期限。
5. 開啟 `/app/dashboard.html`，確認卡點儀表板仍可載入。

## 已知取捨

- Demo seed 以 `demo_simplified: true` 標記；不是完整行政規則數位化，也不保證最終核定。
- LLM 沒有金鑰、逾時或失敗時，會使用 deterministic demo fallback，現場流程仍能繼續。
- 表單 mapping 只覆蓋官方 pack 已提供的欄位；需要人工確認的欄位維持可編輯。
