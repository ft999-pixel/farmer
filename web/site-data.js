/* 農民補給站——前端共用示範資料與期限邏輯
 * 資料鏡射 data/programs/*.json（後端 /programs 之後可直接取代 AID.programs）。
 * 期限膠囊規則：橘＝剩 N 天（受理中）｜灰＝常態受理或尚未開放。
 */
window.AID = (function () {
  // 八類介面分類（對齊田邊好幫手篩選軸；icon 為線條 SVG path）
  const categories = [
    { name: '遇到天災怎麼辦', icon: '<path d="M12 22a7 7 0 1 1 14-1 5 5 0 0 1-1 10H13a6 6 0 0 1-1-9z"/><path d="M16 34l-2 4M23 34l-2 4M30 34l-2 4"/>' },
    { name: '保險保障',       icon: '<path d="M20 6l11 4v9c0 8-5 13-11 15-6-2-11-7-11-15v-9z"/><path d="M15 20l4 4 7-8"/>' },
    { name: '蓋設施、買農機', icon: '<path d="M8 32V18l12-8 12 8v14"/><path d="M8 32h24M16 32v-8h8v8"/>' },
    { name: '借錢週轉',       icon: '<circle cx="20" cy="20" r="13"/><path d="M15 15l10 10M15 25c3-2 7-2 10 0M15 15c3 2 7 2 10 0"/>' },
    { name: '我要開始務農',   icon: '<path d="M20 34V20"/><path d="M20 22c0-6-4-10-10-10 0 6 4 10 10 10zM20 18c0-5 3-8 8-8 0 5-3 8-8 8z"/>' },
    { name: '種植與給付',     icon: '<path d="M12 34V14M20 34V10M28 34V16"/><path d="M12 18l-4-4M20 14l4-4M28 20l4-4"/>' },
    { name: '驗證與外銷',     icon: '<rect x="8" y="12" width="24" height="20" rx="2"/><path d="M8 18h24M15 25l3 3 7-7"/>' },
    { name: '生活照顧',       icon: '<path d="M20 33S7 25 7 16a6.5 6.5 0 0 1 13-1 6.5 6.5 0 0 1 13 1c0 9-13 17-13 17z"/>' }
  ];

  // 示範補助（5 筆，鏡射 data/programs/*.json；uiCategory／industry／region 為前端展示欄位）
  const programs = [
    {
      id: 'moa-disaster-cash-sample-2026',
      name: '農業天然災害現金救助（示範公告：芒果）',
      uiCategory: '遇到天災怎麼辦', industry: '農', region: '全國',
      amountText: '每公頃 9 萬元',
      office: '公所農業課受理', agency: '農糧署（示範）',
      window: { type: '公告型', open: '2026-08-01', close: '2026-08-14' },
      lastVerified: '2026-08-10'
    },
    {
      id: 'afa-crop-insurance-sample',
      name: '農業保險保費補助（示範：芒果／水稻險）',
      uiCategory: '保險保障', industry: '農', region: '全國',
      amountText: '保費補助・中央補助 1/2 起',
      office: '產險公司／農漁會銷售', agency: '農業金融署',
      window: { type: '常態', note: '各品項有投保期，依保單而定' },
      lastVerified: '2026-08-10'
    },
    {
      id: 'afa-green-payment-enrollment',
      name: '綠色環境給付申報',
      uiCategory: '種植與給付', industry: '農', region: '全國',
      amountText: '轉契作獎勵／稻作直接給付等',
      office: '公所或農會受理', agency: '農糧署',
      window: { type: '公告型', open: '2027-01-01', close: '2027-01-31', note: '每年 1 月受理' },
      lastVerified: '2026-08-10'
    },
    {
      id: 'moa-occupational-injury',
      name: '農民職業災害保險給付',
      uiCategory: '保險保障', industry: '農', region: '全國',
      amountText: '傷病／就醫津貼等，依給付類別',
      office: '基層農會受理', agency: '農業部（勞保局核付）',
      window: { type: '常態', note: '受傷後儘速向農會申請' },
      lastVerified: '2026-08-10'
    },
    {
      id: 'moa-retirement-savings',
      name: '農民退休儲金',
      uiCategory: '生活照顧', industry: '農', region: '全國',
      amountText: '政府相對提繳，依月提繳比率',
      office: '基層農會受理', agency: '農業部（勞保局核付）',
      window: { type: '常態', note: '隨時可至農會辦理' },
      lastVerified: '2026-08-10'
    }
  ];

  // 期限資訊：active（受理中，橘）／upcoming（未開放，灰）／always（常態，灰）／closed
  function deadlineInfo(p, today) {
    const t = today ? new Date(today) : new Date();
    t.setHours(0, 0, 0, 0);
    const w = p.window || {};
    if (w.type !== '公告型' || !w.close) {
      return { kind: 'always', label: '常態受理', note: w.note || '' };
    }
    const open = new Date(w.open + 'T00:00:00');
    const close = new Date(w.close + 'T00:00:00');
    if (t > close) return { kind: 'closed', label: '已截止' };
    if (t < open) {
      return { kind: 'upcoming', label: (open.getMonth() + 1) + ' 月受理', open, note: w.note || '' };
    }
    const days = Math.round((close - t) / 86400000);
    return { kind: 'active', label: '剩 ' + Math.max(days, 0) + ' 天', days: Math.max(days, 0) };
  }

  function icon(paths) {
    return '<svg width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="#9FF5CF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths + '</svg>';
  }

  return { categories, programs, deadlineInfo, icon };
})();
