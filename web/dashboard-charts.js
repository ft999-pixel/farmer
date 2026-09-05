/* 卡點儀表板圖表：dashboard.html 與 index.html 共用。
 *
 * 原本寫在 dashboard.html 的行內 script。首頁要放同一組圖，
 * 與其複製一份（改一邊忘另一邊），不如抽出來兩頁共用。
 *
 * 每個 render 都會先確認容器存在，所以頁面只放部分圖表也不會壞。
 * 配色是為深色底設計的，用在淺底頁面要自己給深色背景。
 */
// 前 4 色刻意拉開色相（預設顯示前 4 名），後面才回到綠色系
// 深色底：整組換成高亮度色，原本的深墨綠在深底會隱形
const PALETTE = ['#02DF82','#FF8A5C','#5AB6F5','#FFD24D','#C79BF0','#7FE5C4','#FF9EC4','#9FF5CF'];
const $ = id => document.getElementById(id);
let weeks = 8;

function colorOf(i){ return PALETTE[i % PALETTE.length]; }
const esc = s => String(s ?? '').replace(/[<>&"]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));

// ---- 全國災害救助趨勢（官方統計）--------------------------------------
const C_HOUSE = '#02DF82', C_AMOUNT = '#5AB6F5';

function renderYearly(rows){
  const box = $('chart-yearly');
  if (!box) return;
  if (!rows || !rows.length) { box.innerHTML = '<p class="empty">沒有資料。</p>'; return; }
  const W = 900, H = 300, P = {t: 18, r: 16, b: 40, l: 62};
  const maxH = Math.max(...rows.map(r => r.households));
  const maxA = Math.max(...rows.map(r => r.amount));
  const x = i => P.l + i * (W - P.l - P.r) / Math.max(1, rows.length - 1);
  // 兩條線量級不同，各自正規化後疊在同一張圖，只看趨勢不比絕對值
  const y = (v, max) => P.t + (1 - v / max) * (H - P.t - P.b);

  const grid = [0, .25, .5, .75, 1].map(f => {
    const v = Math.round(maxH * f);
    return `<line x1="${P.l}" y1="${y(v, maxH)}" x2="${W - P.r}" y2="${y(v, maxH)}" stroke="rgba(159,217,194,.16)"/>
      <text x="${P.l - 10}" y="${y(v, maxH) + 4}" text-anchor="end" font-size="11" fill="#9FD9C2">${(v / 1000).toFixed(0)}k</text>`;
  }).join('');
  const ticks = rows.map((r, i) =>
    `<text x="${x(i)}" y="${H - 14}" text-anchor="middle" font-size="11" fill="#9FD9C2">${r.year}</text>`).join('');

  const line = (key, max, color) => {
    const pts = rows.map((r, i) => `${x(i)},${y(r[key], max)}`).join(' ');
    const area = `${P.l},${H - P.b} ${pts} ${x(rows.length - 1)},${H - P.b}`;
    const dots = rows.map((r, i) =>
      `<circle class="spark-dot" cx="${x(i)}" cy="${y(r[key], max)}" r="4.5" fill="${color}">
        <title>${r.year}（民國 ${r.year_roc}）：${r[key].toLocaleString()} ${key === 'households' ? '戶' : '萬元'}</title>
      </circle>`).join('');
    return `<polygon points="${area}" fill="${color}" opacity=".10"/>
      <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.5"
        stroke-linejoin="round" stroke-linecap="round"/>${dots}`;
  };

  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
      ${grid}${ticks}${line('amount', maxA, C_AMOUNT)}${line('households', maxH, C_HOUSE)}
    </svg>
    <div class="chart-legend">
      <span><i style="background:${C_HOUSE}"></i>救助農戶數</span>
      <span><i style="background:${C_AMOUNT}"></i>核定救助金額</span>
    </div>`;
}

// ---- 近五年各類災害（南丁格爾玫瑰圖，類型為推估）------------------------
// 每一瓣角度相同，半徑用「數值開平方」，這樣**面積**才與數值成正比。
// 若半徑直接等比於數值，面積會變成平方關係，視覺上會誇大差距。
function renderDisaster(data){
  const box = $('chart-disaster');
  if (!box) return;
  const rows = data.rows || [], types = data.types || [];
  if (!rows.length) { box.innerHTML = '<p class="empty">沒有資料。</p>'; return; }

  // 五年合計，每一類一瓣
  const totals = types.map(t => ({t, v: rows.reduce((n, r) => n + (r[t] || 0), 0)}))
                      .sort((a, b) => b.v - a.v);
  const sum = totals.reduce((n, d) => n + d.v, 0);
  const maxV = totals[0].v;

  // R 留出邊界空間給短花瓣的外標，否則文字會被畫布裁掉
  const S = 420, C = S / 2, R = 148, GAP = 0.022;   // GAP：花瓣之間留縫
  const step = Math.PI * 2 / totals.length;
  const pt = (r, a) => [C + r * Math.cos(a - Math.PI / 2), C + r * Math.sin(a - Math.PI / 2)];

  const petals = totals.map((d, i) => {
    const r = R * Math.sqrt(d.v / maxV);
    const a0 = i * step + GAP, a1 = (i + 1) * step - GAP;
    const [x0, y0] = pt(r, a0), [x1, y1] = pt(r, a1);
    const big = (a1 - a0) > Math.PI ? 1 : 0;
    const path = `M${C} ${C}L${x0} ${y0}A${r} ${r} 0 ${big} 1 ${x1} ${y1}Z`;
    const pct = (d.v / sum * 100).toFixed(1);
    const mid = (a0 + a1) / 2;
    // 短花瓣放不下字，改標在瓣外並拉一條細線指過去，避免小瓣的數字互相重疊
    const inside = r > 92;
    const [lx, ly] = pt(inside ? r * 0.6 : r + 26, mid);
    const leader = inside ? '' :
      (() => { const [sx, sy] = pt(r + 4, mid), [ex, ey] = pt(r + 16, mid);
        return `<line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" stroke="${colorOf(i)}" stroke-width="1.5"/>`; })();
    return `<path d="${path}" fill="url(#pet${i})" stroke="var(--surface)" stroke-width="2">
        <title>${esc(d.t)}：${d.v.toLocaleString()} 戶（${pct}%）</title>
      </path>${leader}
      <text x="${lx}" y="${ly}" text-anchor="middle" font-size="${inside ? 15 : 12.5}" font-weight="700"
        fill="${inside ? '#06301F' : colorOf(i)}" pointer-events="none"
        dominant-baseline="middle">${pct}%</text>`;
  }).join('');

  const defs = totals.map((d, i) => {
    const c = colorOf(i);
    return `<radialGradient id="pet${i}" cx="50%" cy="50%" r="70%">
      <stop offset="0%" stop-color="${c}" stop-opacity=".55"/>
      <stop offset="100%" stop-color="${c}" stop-opacity="1"/>
    </radialGradient>`;
  }).join('');

  // 圈出最大半徑當比例尺，讓人知道花瓣長度不是隨便畫的
  const rings = [0.5, 1].map(f =>
    `<circle cx="${C}" cy="${C}" r="${R * f}" fill="none" stroke="rgba(159,217,194,.14)"/>`).join('');

  box.innerHTML = `<div class="rose-wrap">
      <svg viewBox="0 0 ${S} ${S}" class="rose"><defs>${defs}</defs>${rings}${petals}</svg>
      <table class="cat-table">${totals.map((d, i) => `
        <tr>
          <td><i class="dot" style="background:${colorOf(i)}"></i>${esc(d.t)}</td>
          <td class="n">${d.v.toLocaleString()}</td>
          <td class="pct">${(d.v / sum * 100).toFixed(1)}%</td>
        </tr>`).join('')}
        <tr><td><b>五年合計</b></td><td class="n"><b>${sum.toLocaleString()}</b></td><td class="pct">戶</td></tr>
      </table>
    </div>`;
}

function renderKpi(s){
  if (!$('kpi')) return;   // 首頁只放圖表輪播，沒有 KPI 卡
  const top = s.ranking[0];
  const topCat = s.by_category[0];
  const t = s.by_level.totals, known = t['中央'] + t['縣市'];
  const localPct = known ? Math.round(t['縣市'] / known * 100) + '%' : '—';
  $('kpi').innerHTML = `
    <div class="kpi"><b>${s.total}</b><span>期間內回報卡點</span></div>
    <div class="kpi"><b style="font-size:20px">${top ? top.reason : '—'}</b><span>最常見卡點${top ? '（' + top.count + ' 筆）' : ''}</span></div>
    <div class="kpi"><b style="font-size:20px">${topCat ? topCat.category : '—'}</b><span>最卡人的補助類別${topCat ? '（' + topCat.count + ' 筆）' : ''}</span></div>
    <div class="kpi"><b>${localPct}</b><span>卡點發生在地方公所</span></div>`;
}

const C_DOC = '#02DF82', C_STUCK = '#FFD24D';   // 來源固定兩色，跨列可比
const C_CENTRAL = '#5AB6F5', C_LOCAL = '#FFD24D';

// 熱力圖：五階跨色相（深綠→青→黃→橙→紅）。
// 深色底不能沿用淺色主題的「淺黃起頭」，最低階必須接近底色才看得出強弱。
const HEAT = [
  ['#0F4B36', '#9FD9C2'], ['#177F5A', '#EAFBF3'], ['#4FC98F', '#06301F'],
  ['#FFD24D', '#06301F'], ['#FF7A45', '#2A0F06'],
];
function heatColor(ratio){
  return HEAT[Math.min(HEAT.length - 1, Math.floor(ratio * HEAT.length - 1e-9))];
}

function renderBar(s){
  const box = $('chart-bar');
  if (!box) return;
  if (!s.ranking.length) { box.innerHTML = '<p class="empty">期間內沒有卡點回報。</p>'; return; }
  const max = s.ranking[0].count;
  const bars = s.ranking.map(r => {
    const doc = r.by_source['公文'] || 0, stuck = r.count - doc;
    const w = c => (c / max * 100).toFixed(1) + '%';
    return `<div class="bar-row" title="公文 ${doc} 筆／我卡住了 ${stuck} 筆">
      <div class="name">${r.reason}</div>
      <div class="bar-track" style="width:100%">
        <i style="width:${w(doc)};background:${C_DOC}"></i>
        <i style="width:${w(stuck)};background:${C_STUCK}"></i>
      </div>
      <div class="num">${r.count}</div></div>`;
  }).join('');
  box.innerHTML = bars + `<div class="legend" style="margin-top:14px">
    <span><i style="background:${C_DOC}"></i>公文寫的理由</span>
    <span><i style="background:${C_STUCK}"></i>農民自述（我卡住了）</span></div>`;
}

// ② 補助類別：類別數少且是「占整體多少」→ 甜甜圈比長條更快看出比重
function renderCategory(s){
  const box = $('chart-cat');
  if (!box) return;
  const rows = s.by_category;
  if (!rows.length) { box.innerHTML = '<p class="empty">尚無標記補助類別的卡點。</p>'; return; }
  const total = rows.reduce((n, r) => n + r.count, 0);
  const R = 92, RI = 56, C = 110;
  const pt = (r, a) => [C + r * Math.cos(a), C + r * Math.sin(a)];
  let start = -Math.PI / 2;
  const arcs = rows.map((r, i) => {
    const ang = r.count / total * Math.PI * 2;
    const end = start + ang;
    const big = ang > Math.PI ? 1 : 0;
    const [x0, y0] = pt(R, start), [x1, y1] = pt(R, end);
    const [x2, y2] = pt(RI, end), [x3, y3] = pt(RI, start);
    const d = `M${x0} ${y0}A${R} ${R} 0 ${big} 1 ${x1} ${y1}L${x2} ${y2}A${RI} ${RI} 0 ${big} 0 ${x3} ${y3}Z`;
    start = end;
    return `<path d="${d}" fill="${colorOf(i)}" stroke="var(--surface)" stroke-width="2"><title>${r.category} ${r.count} 筆</title></path>`;
  }).join('');
  const rowsHtml = rows.map((r, i) => `
    <tr>
      <td><i class="dot" style="background:${colorOf(i)}"></i>${r.category}</td>
      <td class="n">${r.count}</td>
      <td class="pct">${Math.round(r.count / total * 100)}%</td>
      <td class="note">最常卡在 <b>${r.top_reason}</b>（${r.top_count} 筆）</td>
    </tr>`).join('');
  box.innerHTML = `<div class="donut-wrap">
      <svg viewBox="0 0 220 220" class="donut">${arcs}
        <text x="${C}" y="${C - 4}" text-anchor="middle" font-size="30" font-weight="700" fill="#EAFBF3">${total}</text>
        <text x="${C}" y="${C + 18}" text-anchor="middle" font-size="13" fill="#9FD9C2">筆卡點</text>
      </svg>
      <table class="cat-table">${rowsHtml}</table>
    </div>`;
}

// ③ 中央 vs 縣市：重點是「兩者差多少、偏哪邊」→ 啞鈴圖直接把差距畫成一段線
function renderLevel(s){
  const box = $('chart-level'), d = s.by_level;
  if (!box) return;
  if (!d.rows.length) {
    box.innerHTML = '<p class="empty">尚無可判斷機關層級的卡點。公文回報時帶上發文機關即可統計。</p>';
    return;
  }
  const rows = [...d.rows].sort((a, b) => (b['縣市'] - b['中央']) - (a['縣市'] - a['中央']));
  const max = Math.max(1, ...rows.map(r => Math.max(r['中央'], r['縣市'])));
  const W = 900, RH = 38, L = 140, Rp = 105, H = rows.length * RH + 34;
  const x = v => L + v / max * (W - L - Rp);
  const grid = [0, .25, .5, .75, 1].map(f => {
    const v = Math.round(max * f);
    return `<line x1="${x(v)}" y1="6" x2="${x(v)}" y2="${rows.length * RH}" stroke="rgba(159,217,194,.22)"/>
            <text x="${x(v)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="#9FD9C2">${v}</text>`;
  }).join('');
  const body = rows.map((r, i) => {
    const y = i * RH + RH / 2;
    const a = r['中央'], b = r['縣市'];
    const [lo, hi] = a <= b ? [a, b] : [b, a];
    const lean = b > a ? '地方' : (a > b ? '中央' : '');
    return `<text x="${L - 12}" y="${y + 4}" text-anchor="end" font-size="13.5" font-weight="500" fill="#EAFBF3">${r.reason}</text>
      <line x1="${x(lo)}" y1="${y}" x2="${x(hi)}" y2="${y}" stroke="rgba(159,217,194,.45)" stroke-width="3" stroke-linecap="round"/>
      <circle cx="${x(a)}" cy="${y}" r="7" fill="${C_CENTRAL}"><title>中央 ${a} 筆</title></circle>
      <circle cx="${x(b)}" cy="${y}" r="7" fill="${C_LOCAL}"><title>縣市 ${b} 筆</title></circle>
      <text x="${x(hi) + 14}" y="${y + 4}" font-size="12" font-weight="700" fill="#9FD9C2">${lean ? lean + ' +' + (hi - lo) : '持平'}</text>`;
  }).join('');
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">${grid}${body}</svg>
    <div class="legend" style="margin-top:6px">
      <span><i class="dot" style="background:${C_CENTRAL}"></i>中央（合計 ${d.totals['中央']}）</span>
      <span><i class="dot" style="background:${C_LOCAL}"></i>縣市（合計 ${d.totals['縣市']}）</span>
      <span style="color:var(--ink-soft)">線段長度＝兩者差距，依偏向地方的程度排序</span>
    </div>` + (d.unknown ? `<p class="hint" style="margin:8px 0 0">另有 ${d.unknown} 筆無法判斷層級，未列入本圖。</p>` : '');
}

function renderHeat(s){
  const box = $('chart-heat');
  if (!box) return;
  const m = s.matrix;
  if (!m.categories.length) {
    box.innerHTML = '<p class="empty">尚無「補助類別」標記的卡點。公文回報時帶上 category 欄位即可統計。</p>';
    return;
  }
  const max = Math.max(1, ...m.cells.flat());
  const cell = v => {
    if (!v) return `<td style="background:rgba(255,255,255,.05);color:rgba(159,217,194,.5)">·</td>`;
    const [bg, fg] = heatColor(v / max);
    return `<td style="background:${bg};color:${fg}">${v}</td>`;
  };
  box.innerHTML = `<table class="heat"><tr><th></th>${
    m.reasons.map(r => `<th class="col">${r}</th>`).join('')}</tr>${
    m.categories.map((c, i) => `<tr><th class="row">${c}</th>${
      m.cells[i].map(cell).join('')}</tr>`).join('')}</table>
    <div class="heat-key">
      <span>少</span>
      ${HEAT.map(([bg]) => `<i style="background:${bg}"></i>`).join('')}
      <span>多（最高 ${max} 筆）</span>
    </div>`;
}

async function load(){
  const s = await (await fetch(`/blockers/stats?weeks=${weeks}`)).json();
  // 逐張畫並各自吃掉錯誤：一張圖畫壞不該讓後面五張跟著空白
  [renderKpi, renderBar, renderCategory, renderLevel, renderHeat].forEach(fn => {
    try { fn(s); } catch (e) { console.error(fn.name, e); }
  });
}

// 全國統計不隨「期間」切換而變，載入一次就好
async function loadDisasterStats(){
  try {
    const d = await (await fetch('/disaster-stats')).json();
    renderYearly(d.yearly.rows);
    renderDisaster(d.by_disaster);
  } catch (e) {
    console.error('disaster-stats', e);
    if ($('chart-yearly')) $('chart-yearly').innerHTML = '<p class="empty">載入不到全國統計資料。</p>';
    if ($('chart-disaster')) $('chart-disaster').innerHTML = '';
  }
}

// 各頁自己決定要載入什麼、要不要工具列（首頁沒有期間切換）
window.DashboardCharts = {
  setWeeks(n){ weeks = n; },
  load, loadDisasterStats,
  loadAll(){ load(); loadDisasterStats(); },
};
