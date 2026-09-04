# 預填表單服務

## 啟動
python app.py
或
venv\Scripts\python app.py

## 使用
1. 開啟 http://127.0.0.1:5000
2. 選擇申請表
3. 確認預填欄位，補齊剩餘內容
4. 點預覽 / 下載 PDF

## API
POST /api/templates 建立模板
GET /api/templates 列表
GET /api/templates/<id>/versions 版本
GET /api/template-versions/<id>/fields 欄位定義
GET /api/template-versions/<id>/pdf 原始 PDF
POST /api/applications 建立申請
PATCH /api/applications/<id> 更新
POST /api/profiles 寫入本機 profile

## 前端資料
IndexedDB 儲存 profile / application，首次會從 /api/profiles 同步種子資料。
