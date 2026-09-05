# 預填表單服務

## 啟動
在 `module/prefill` 目錄執行：

```bash
python app.py
```

啟動時會自動把 `afa115_form_templates/afa115_templates.json` 匯入本機 SQLite；重複啟動不會建立重複模板。資料庫預設在 `module/prefill/data/form.db`，也可以用 `PREFILL_DB` 指定其他路徑。

或
venv\Scripts\python app.py

## 使用
1. 開啟 http://127.0.0.1:5000
2. 選擇申請表
3. 確認預填欄位，補齊剩餘內容
4. 點預覽 / 下載 PDF

目前 AFA 115 模板使用 `data/uploads/` 內的本機 PDF。原始 50 頁文件保留為
`afa115-source-1150717.pdf`，附表 6、9、13、18、19 已各自拆成單頁 PDF，並由模板的
`pdf_path` 指向。`source_pdf_url` 僅作來源紀錄，服務不會為預覽或下載連線到遠端來源。

若尚未放入對應的本機 PDF 或校準座標，預覽／下載填妥 PDF 會保持停用；這樣不會把內容疊到錯誤位置。

## API
POST /api/templates 建立模板
GET /api/templates 列表
GET /api/templates/<id>/versions 版本
GET /api/template-versions/<id>/fields 欄位定義
GET /api/template-versions/<id>/pdf 本機原始 PDF
POST /api/applications 建立申請
PATCH /api/applications/<id> 更新
POST /api/profiles 寫入本機 profile

## 前端資料
IndexedDB 儲存 profile / application，首次會從 /api/profiles 同步種子資料。

欄位定義除了 `field_key / label / type / required / editable / prefill_source` 外，也會回傳 `note / privacy / options / coordinates_calibrated`。AFA 115 的身分證字號、戶籍地址等 `local_only` 欄位只在瀏覽器本機處理；儲存草稿也只寫入 IndexedDB，不會呼叫 `/api/applications`。
