# AFA 115 農機補助表單模板

這組模板是依「115 年省工高效及碳匯農機補助實施計畫」整理，
目前包含：

- 附表 6：農事服務機械補助申請書（PDF 第 31 頁）
- 附表 9：省工農業機械／新研發農機補助申請書（PDF 第 34 頁）
- 附表 13：碳匯農機補助申請書（PDF 第 38 頁）
- 附表 18：農機所有人部分個資公開使用授權同意書（PDF 第 43 頁）
- 附表 19：配合調度暨相關事項切結書（PDF 第 44 頁）

## 與現有 `module/prefill` 的對接

現有 backend 已有：
- templates
- template_versions
- form_fields

這份 JSON 的 `fields` 可以轉成 `form_fields`。
`field_key / label / type / required / editable / prefill_source` 可直接沿用。

## 重要：local-only

以下資料不應送回 server：
- 身分證統一編號
- 戶籍地址
- 使用者在瀏覽器修改後的完整申請內容

模板本身可以存在 DB；值存在 IndexedDB。

## 尚需做的一步

現有 `form_fields` 需要 PDF 座標（pos_x / pos_y / width / height）。
這份第一版先把：
1. 官方表單來源
2. 對應 PDF 頁碼
3. 欄位語意
4. prefill_source
5. privacy

整理好。

正式上線前，建議將官方 PDF 的對應頁裁成單頁 PDF，再用 box picker 校準座標。
