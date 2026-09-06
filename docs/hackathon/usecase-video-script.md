# Farmer Aid Station — Use-Situation Video｜分鏡腳本

> 貼進 prompt_animation 的 `=== CONTENT TO ANIMATE ===` 區塊。
> **14 個 scene／85 秒**，平均一鏡 6 秒。每鏡都標好 3D 技法、進場層次（data-at）、循環動態、字幕行。
> 改寫自 apicta-video-script.md：由論述式（問題→解法→迴路）改為情境式，全片跟著同一位芒果農走完 14 天。

---

## Topic / One-Line Pitch

Farmer Aid Station — a farmer says one sentence in his own language, and the scattered world of agricultural subsidies becomes a short, ordered list of what to do next.

## Total Target Duration

85 seconds · 14 scenes

## Caption Language

English captions only.
畫面內 UI 文字一律保留繁體中文，英文放在下方小一號。**語言落差本身就是故事，不要把介面翻掉。**

## 全片節奏表

| # | 時間 | 幕 | 一句話 |
|---|---|---|---|
| 01 | 0–7 | I 早晨 | 颱風過後的果園 |
| 02 | 7–14 | I 早晨 | 補助之牆：它們都在，他找不到 |
| 03 | 14–20 | II 開口 | 他講一句台語 |
| 04 | 20–26 | II 開口 | 口語變成結構化事實 |
| 05 | 26–32 | II 開口 | 空白欄位決定下一題 |
| 06 | 32–39 | III 清單 | 三層清單成形 |
| 07 | 39–46 | III 清單 | 優先卡展開：文件、電話、期限 |
| 08 | 46–52 | III 清單 | 「先不用看」也給原因＋免責 |
| 09 | 52–58 | IV 公文 | 掛號信來了 |
| 10 | 58–64 | IV 公文 | 拍一張照 |
| 11 | 64–68 | IV 公文 | 白話卡＋期限反問 |
| 12 | 68–74 | V 卡住 | 我卡住了：一鍵三選項 |
| 13 | 74–80 | V 卡住 | 雙分支：接住他／餵給政府 |
| 14 | 80–85 | V 卡住 | 結尾：DAY 14 · 領到了 |

---

# 幕一 · 早晨（0–14s）

## Scene 01 ｜ 0:00–0:07 ｜ 颱風過後

**3D 技法：** parallax stacked layers（四層 z 軸視差）＋緩慢右移的 camera drift

**畫面層次（data-at）**
- `data-at 0` — 最遠層：灰藍天光，一道低矮山稜線，translateZ(-400px)
- `data-at 0.5` — 中景：一排歪斜的芒果樹剪影，translateZ(-160px)，各自 3–5 度輕微擺動（風還沒停）
- `data-at 1.5` — 近景：五顆落地芒果，translateZ(0)～(60px)，逐顆 fade+drop-in，落點錯開
- `data-at 2.5` — `.subtitle`：`A MORNING IN AUGUST`
- `data-at 3.5` — `.title`：`The help already <hl>exists</hl>.`
- `data-at 5` — `.note`：`Dozens of programs. Different agencies, different forms, different deadlines. None of them come looking for him.`
- `data-at 6` — 右上角極小 mono 計數器：`DAY 1`（不解釋，全片持續出現）

**循環動態：** 樹剪影 8s ease-in-out 無限擺動；落地芒果各自 6s 微幅呼吸縮放；最遠層 20s linear 極慢平移。

**字幕（subs）**
- `0.5–3.5` — `The typhoon passed at three in the morning.`
- `3.5–7` — `By sunrise, the relief programs were already open.`

---

## Scene 02 ｜ 0:07–0:14 ｜ 補助之牆

**3D 技法：** z-axis 深度陣列 — 24 張補助名稱小卡沿 z 軸退進遠方，愈遠愈模糊愈小，形成一面讀不完的牆

**畫面層次（data-at）**
- `data-at 0` — 24 張 `.prog-chip` 依序在 0–1.2s 內以 stagger 湧入，z 從 -1200px 排到 0，blur 隨距離增加
- 卡片文字（可辨識的只有最前四張，其餘刻意糊掉）：`天然災害現金救助` · `農業保險保費補助` · `農機補助` · `青年從農貸款`
- `data-at 2` — `.subtitle`：`FORTY-ONE PROGRAMS RUNNING`
- `data-at 3` — `.title`：`He is not short of <hl>help</hl>. He is short of a <hl>way in</hl>.`
- `data-at 4.5` — 一隻半透明的手從畫面下緣伸入，停在最近的卡前面，沒有碰到（構圖上要「差一點」）
- `data-at 5.5` — 背景日曆頁 3 張連續掀飛，橘色 `#D85A30` 一閃：`DEADLINE`

**循環動態：** 整面卡牆極慢 rotateY ±3 度來回（像呼吸的檔案櫃）；最前排卡片 z 軸微幅前後浮動。

**字幕**
- `7–10.5` — `Forty-one programs. Eight agencies. Zero of them will call him.`
- `10.5–14` — `And one of them closes in nine days.`

---

# 幕二 · 開口（14–32s）

## Scene 03 ｜ 0:14–0:20 ｜ 他講一句台語

**3D 技法：** 3D conversation bubble — 一顆大的對話泡從畫面下方以 rotateX(-25deg) 浮起並轉正

**畫面層次（data-at）**
- `data-at 0` — 空的對話泡浮起，白底、大圓角、深綠邊
- `data-at 0.8` — 泡內出現聲波：7 根綠色豎條隨機起伏（ASR 收音中）
- `data-at 1.5` — 台語原句以逐字打字機效果出現，48px 以上：`阮的檨仔攏落了了`
- `data-at 3` — 下方英文小一號淡入：`"My mangoes are all down."`
- `data-at 4` — `.subtitle`：`NO FORM. NO SEARCH BOX.`
- `data-at 4.5` — `.title`：`He just <hl>says it</hl>.`
- `data-at 5.5` — `.note`：`In Taiwanese. In one sentence. That is the entire input.`

**循環動態：** 聲波豎條 1.2s linear infinite 起伏；對話泡 5s 上下浮 6px。

**字幕**
- `14–17` — `He doesn't search. He doesn't filter.`
- `17–20` — `He says one sentence, in the language he actually speaks.`

---

## Scene 04 ｜ 0:20–0:26 ｜ 口語變成事實

**3D 技法：** 對話泡向後退到 z(-300px) 並降低透明度，四張 `.fact-chip` 從泡中「掉出來」並飛到前景排成一列

**畫面層次（data-at）**
- `data-at 0` — 上一鏡的對話泡縮小後退，固定在畫面上緣當作來源
- `data-at 0.6` — chip 1 飛出：`crop: 芒果 / mango` ✅ 綠框
- `data-at 1.2` — chip 2 飛出：`event: 颱風災損 / typhoon damage` ✅ 綠框
- `data-at 1.8` — chip 3 落定但**空白**：`township: —` ⬜ 灰虛線框，開始脈動
- `data-at 2.4` — chip 4 落定但**空白**：`land: —` ⬜ 灰虛線框，開始脈動
- `data-at 3.5` — `.subtitle`：`UNDERSTOOD, NOT INTERROGATED`
- `data-at 4` — `.title`：`One sentence. <hl>Two facts</hl>. Two blanks.`
- `data-at 5` — `.note`：`The model only extracts and rewrites. It never decides which programs to recommend — a rule engine does.`

**循環動態：** 兩張空白 chip 以 1.6s ease-in-out 無限脈動（虛線框亮度變化）；已填 chip 靜止微亮。

**字幕**
- `20–23` — `The sentence becomes structured facts.`
- `23–26` — `Two of them come back blank. That is not a failure.`

---

## Scene 05 ｜ 0:26–0:32 ｜ 空白決定下一題

**3D 技法：** 空白 chip 向上「拉出」一條光線，接到一張 rotateX(-10deg) 的提問卡；一次只有一張卡

**畫面層次（data-at）**
- `data-at 0` — `township: —` 那張 chip 亮起，一條細綠線往上長出
- `data-at 0.8` — 提問卡展開（大字、只有一題）：`你的田在哪個鄉鎮？` ／ `Which township is your land in?`
- `data-at 1.6` — 卡下方三個大按鈕：`玉井區` `南化區` `其他` — 手寫感輕微歪斜
- `data-at 2.6` — `玉井區` 被按下，chip 從虛線變實線綠框：`township: 玉井區`
- `data-at 3.4` — 右側極簡進度點：`● ● ○ ○` 配文字 `3–5 questions, one at a time`
- `data-at 4.2` — `.title`：`The blanks decide <hl>the next question</hl>.`
- `data-at 5` — `.note`：`Never a wall of fields. One question, chosen to narrow things fastest.`

**循環動態：** 綠線有由下往上的流光；未答的進度空心點緩慢脈動。

**字幕**
- `26–29` — `Whatever is missing becomes the next question.`
- `29–32` — `One at a time. Three to five, and it is done.`

> ⚠️ 措辭鐵則：本鏡到片尾，畫面上不得出現 eligible / qualified / approved / you will receive。

---

# 幕三 · 清單（32–52s）

## Scene 06 ｜ 0:32–0:39 ｜ 三層清單成形

**3D 技法：** 三層 tilted 面板沿 y 軸垂直堆疊，各層 rotateX(-8deg)，由上而下依序 slide-in，像三格層架

**畫面層次（data-at）**
- `data-at 0` — `.subtitle`：`WHAT COMES BACK`
- `data-at 0.5` — `.title`：`Not a verdict. A <hl>short list</hl>.`
- `data-at 1.5` — 第一層滑入，綠框 `#02DF82`：`建議優先看` ／ `Recommended to check first` — 內含 2 張卡
- `data-at 2.8` — 第二層滑入，中性框：`可能有關，再回答一題就知道` ／ `Possibly relevant — one more question` — 內含 3 張卡，其中一張卡內嵌一個小提問
- `data-at 4` — 第三層滑入，收合狀灰底：`這次先不用看` ／ `Skip for now` — 只顯示 `6 筆` 與 `點開看原因`
- `data-at 5` — 第一層右上角橘色期限膠囊 `#D85A30` 彈入：`剩 9 天` ／ `9 days left`
- `data-at 6` — 底部常駐免責條淡入（必須清楚可讀）：`實際資格由承辦單位認定` ／ `Final eligibility is determined by the responsible agency.`

**循環動態：** 三層各自以不同相位極慢浮動（差 0.4s），維持層次感；橘色期限膠囊 2s 呼吸。

**字幕**
- `32–35.5` — `Not "you qualify". Not "you don't".`
- `35.5–39` — `Three shelves: look at these first, these might apply, skip these.`

---

## Scene 07 ｜ 0:39–0:46 ｜ 優先卡展開

**3D 技法：** 第一層最上面那張卡放大填滿畫面（flip + scale up），其餘層退到 z(-500px) 並模糊

**畫面層次（data-at）**
- `data-at 0` — 卡片翻正放大：`農業天然災害現金救助（芒果）`
- `data-at 0.8` — 歸因列淡入（這行很重要，一定要在）：`推薦原因：你說「芒果」「颱風」「玉井區」` ／ `Why this: you said mango, typhoon, Yujing.`
- `data-at 1.6` — 文件清單三行依序打勾滑入：`身分證影本` ✓ · `土地文件或使用同意書` ✓ · `農作物照片` ✓
- `data-at 3` — 大顆綠色按鈕彈入（深綠字，禁止白字）：`打給承辦人 049-XXX-XXX` ／ `Call the office`
- `data-at 4` — 地點行：`玉井區公所 農業課` ／ `District office, agriculture desk`
- `data-at 5` — 橘色期限條再次強調並開始跳動：`剩 9 天` ／ `9 days left`
- `data-at 6` — 底部小字：`依據` chip（收合狀，暗示可點開才顯示法條，本鏡不展開）

**循環動態：** 期限條數字每 2s 一次極輕微 scale 脈動；按鈕有緩慢的外擴光暈。

**字幕**
- `39–42.5` — `Every card says why it is there.`
- `42.5–46` — `Which documents. Which desk. Which phone number. How many days left.`

---

## Scene 08 ｜ 0:46–0:52 ｜ 連「不用看」也給原因

**3D 技法：** 鏡頭拉回三層架，第三層向前傾倒展開（rotateX from -8deg to 8deg），露出內容

**畫面層次（data-at）**
- `data-at 0` — 第三層展開，6 張灰卡露出
- `data-at 1` — 其中一張浮起，附一行原因：`這筆限定水稻，你種的是芒果` ／ `This one is rice-only.`
- `data-at 2` — 第二張浮起：`這筆的申請期已經在 7/30 結束` ／ `This one closed on July 30.`
- `data-at 3.2` — 一行溫和的出口句（**不要把否定講死**）：`條件常有例外，打電話問最準` ／ `Exceptions happen. A phone call is still the surest answer.`
- `data-at 4.2` — `.title`：`Even the <hl>no</hl> gets a reason.`
- `data-at 5` — 免責條再次強調，短暫加粗：`實際資格由承辦單位認定`

**循環動態：** 灰卡群輕微 y 軸浮動；出口句底線有一次左到右掃過的光。

**字幕**
- `46–49` — `The ones it sets aside still tell him why.`
- `49–52` — `And it never closes the door — a phone call is still the surest answer.`

---

# 幕四 · 公文（52–68s）

## Scene 09 ｜ 0:52–0:58 ｜ 掛號信來了

**3D 技法：** floating envelope — 一封公文信封從畫面右上以 rotateY(35deg)、rotateX(-15deg) 旋轉飛入，落到中央桌面（桌面用一道柔和陰影暗示）

**畫面層次（data-at）**
- `data-at 0` — `DAY 1` 計數器跳到 `DAY 5`（用一次快速翻牌）
- `data-at 0.6` — 信封飛入落定
- `data-at 1.8` — 信封開啟，公文抽出並展開為 tilted 面板（rotateX(-20deg)）
- `data-at 2.6` — 公文內容浮現：整面密集的公文體中文，**刻意模糊到無法辨識任何機關名**
- `data-at 3.6` — 唯一保持銳利的一行，橘色標記：`文到十五日內`
- `data-at 4.4` — `.subtitle`：`FOUR DAYS LATER`
- `data-at 5` — `.title`：`Written for <hl>offices</hl>. Not for him.`

**循環動態：** 公文面板 6s 極慢傾角來回；那行 `文到十五日內` 每 2.5s 亮一次。

**字幕**
- `52–55` — `Four days later, a letter arrives.`
- `55–58` — `One line in it is sharp. The rest may as well be a wall.`

---

## Scene 10 ｜ 0:58–1:04 ｜ 拍一張照

**3D 技法：** floating phone mockup — 手機以 rotateY(-20deg) 浮在公文上方，螢幕內即時映出下方公文

**畫面層次（data-at）**
- `data-at 0` — 手機浮入，懸停在公文上方
- `data-at 1` — 螢幕四角出現對焦框，收攏對齊公文
- `data-at 1.8` — 快門：全畫面一次極短白閃（`#sceneFlash`）
- `data-at 2.4` — OCR 掃描線由上往下掃過公文，掃過處中文字被逐行「提亮」
- `data-at 3.6` — 掃描完成，公文右側長出一條細線指向畫面右方（暗示即將轉譯）
- `data-at 4.4` — `.title`：`One photo. <hl>That's the whole step.</hl>`
- `data-at 5.2` — `.note`：`Plain text in, plain text out. No voice-over, no extra buttons.`

**循環動態：** 掃描線完成後留一道殘影緩慢淡出；手機 4s 上下浮 8px。

**字幕**
- `58–61` — `He photographs it. That is the entire interaction.`
- `61–64` — `Text goes in. Plain words come back.`

---

## Scene 11 ｜ 1:04–1:08 ｜ 白話卡＋期限反問

**3D 技法：** before/after tilted panels — 左邊模糊公文往左後退並更糊，右邊白話卡往前推到正面

**畫面層次（data-at）**
- `data-at 0` — 左右兩塊面板同時就位，左糊右清
- `data-at 0.6` — 白話卡第一行：`他們要你補一份文件` ／ `They want one more document.`
- `data-at 1.2` — 第二行：`去區公所農業課拿` ／ `Get it at the district office.`
- `data-at 1.8` — 第三行**是一個問句**（本片的小巧思，務必保留）：`你哪一天收到這封信？` ／ `What day did the letter reach you?`
- `data-at 2.4` — 使用者作答：`8/22` 以 chip 落入
- `data-at 2.8` — 期限即時算出，橘色膠囊彈入：`剩 11 天` ／ `11 days left`
- `data-at 3.2` — 底部一行技法註解：`公告型自己倒數。文到型得先問。` ／ `Notices count down on their own. Case letters have to ask.`

**循環動態：** 左側模糊面板持續極慢下沉；右側白話卡三行有依序的微光殘留。

**字幕**
- `64–66` — `"Within fifteen days of receipt" — of which receipt?`
- `66–68` — `So it asks him first, then starts counting.`

---

# 幕五 · 卡住（68–85s）

## Scene 12 ｜ 1:08–1:14 ｜ 我卡住了

**3D 技法：** pop-out spotlight — 畫面壓暗，只有一顆大按鈕被打亮並向前突出（translateZ(80px)）

**畫面層次（data-at）**
- `data-at 0` — `DAY 5` 翻到 `DAY 9`；背景是一張填到一半、停住的申請表（灰、靜止）
- `data-at 1` — 大按鈕浮出並打光：`我卡住了` ／ `"I'm stuck."`
- `data-at 2` — 一次點按：按鈕下沉，漣漪擴散
- `data-at 2.6` — 三個選項以扇形彈出（間隔 0.3s）：
  `太麻煩` ／ `Too complicated`
  `文件生不出來` ／ `Can't get the documents`
  `看不懂` ／ `Don't understand`
- `data-at 4.2` — `.subtitle`：`WHEN IT STOPS WORKING`
- `data-at 4.8` — `.title`：`A button that says <hl>"I give up"</hl> — out loud.`

**循環動態：** 按鈕外圈 2s 呼吸光暈；三個選項各自輕微浮動。

**字幕**
- `68–71` — `Somewhere in the paperwork, he stalls.`
- `71–74` — `One tap. Three honest options.`

---

## Scene 13 ｜ 1:14–1:20 ｜ 雙分支

**3D 技法：** 從按鈕分岔出兩條 3D 路徑，一條往左前方（給他）、一條往右後方（給政府），兩邊同時發生

**畫面層次（data-at）**
- `data-at 0` — 兩條光帶自按鈕分出
- `data-at 0.8` — **左前分支**：兩張新卡片滑入 — `先看看這幾筆，可能比較好辦` ／ `Here are others that may be easier.`
- `data-at 2` — **右後分支**：一張去識別化的鄉鎮地圖從遠處升起（rotateX(55deg) 平躺），數個鄉鎮陸續亮起
- `data-at 3` — 地圖上方標題：`卡點統計` ／ `where people quit`
- `data-at 3.8` — 右側長出三段堆疊長條，各自標示三種原因，數字快速跑動
- `data-at 4.6` — `.note`：`Every abandonment used to be silence. Now it is anonymous data, pointed at the exact step that failed.`
- `data-at 5.2` — 底部免責條再次出現：`實際資格由承辦單位認定`

**循環動態：** 地圖上的鄉鎮亮點以不同相位持續明滅；堆疊長條輕微增長。

**字幕**
- `74–77` — `To him: other programs, easier ones.`
- `77–80` — `To the map: the first record of where people actually quit.`

---

## Scene 14 ｜ 1:20–1:25 ｜ DAY 14

**3D 技法：** 3D extruded text（多層 text-shadow 疊出厚度）＋背景所有前面出現過的元素以極小尺寸緩慢環繞（orbiting recap）

**畫面層次（data-at）**
- `data-at 0` — 背景：芒果、卡片、公文、按鈕縮成小元素，繞著中心緩慢公轉
- `data-at 0.8` — 計數器最後一次翻牌：`DAY 9` → `DAY 14`，並在右側加上綠字 `領到了` ／ `paid`
- `data-at 1.8` — 主標以 3D 厚度浮出：`農民補給站` ／ `Farmer Aid Station`
- `data-at 2.8` — 台語標語，手寫感、輕微歪斜：`甲你鬥相共`
- `data-at 3.4` — 英文一行：`Plain answers, on the farmer's side.`
- `data-at 4.2` — 最底一行小字保留到最後一格：`實際資格由承辦單位認定` ／ `Final eligibility is determined by the responsible agency.`

**循環動態：** 環繞元素 24s linear 無限公轉；主標厚度層有極慢的光源移動。

**字幕**
- `80–83` — `Day 14. The money is in.`
- `83–85` — `Farmer Aid Station — plain answers, on the farmer's side.`

---

## Optional Palette / Font Overrides

覆蓋參考檔的藍配色，改用本產品品牌色：

```
--bg:        #F7FBF8
--bg2:       #EAF6EE
--card:      #ffffff
--teal:      #02DF82   /* 品牌綠：按鈕、主要強調、.hl */
--teal-soft: rgba(2,223,130,0.10)
--coral:     #D85A30   /* 專用於期限急迫，不得他用 */
--coral-soft:rgba(216,90,48,0.10)
--navy:      #06301F   /* 深墨綠：所有文字 */
--text:      #06301F
--muted:     rgba(6,48,31,0.70)
--border:    rgba(6,48,31,0.08)
--shadow:    0 2px 20px rgba(6,48,31,0.06)
```

**對比鐵則：** `#02DF82` 上面只能放 `#06301F` 文字，**永遠不要白字配綠底**。

字體：heading 與 body 皆改為 `'GenSenRounded TC', 'Chiron GoRound TC', sans-serif`；mono 保留 `'DM Mono'`。字重 H1=900、H2=700、按鈕=500、內文=400。

---

## Hard constraints — 原文照抄給模型

1. 系統只有三項功能：補助媒合、公文白話翻譯、「我卡住了」回饋迴路。**不得自行新增第四項。**
2. 絕不出現 eligible / qualified / approved / meets the requirements / you will receive。系統只推薦，資格由承辦單位認定。`實際資格由承辦單位認定` 必須出現在 Scene 06、08、13、14。
3. 不得出現或指名任何入口通路或通訊軟體。
4. 法條依據不主動顯示，最多只做成收合的 `依據` chip（Scene 07），本片不展開。
5. 不得出現真實機關名稱或可辨識的公文抬頭，一律模糊處理。
6. 公文翻譯是純文字：沒有語音播放、沒有額外行動卡片。
7. 每個 scene 都必須具備 `.subtitle` + `.title`（含至少一個 `.hl`）+ 3D 視覺 + `.note`，四者用 data-at 在該鏡前 6 秒內依序進場。
