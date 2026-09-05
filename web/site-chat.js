/* 農民補給站——共用對話元件（首頁內嵌＋chat.html 全頁共用）
 * 用法：AidChat.init(container, { docTab: true })
 * 長輩規格：選項按鈕 ≥52px、文字 ≥19px（1.1875rem）、選項用按的不用打字。
 * 措辭鐵則：不出現「符合／不符合／資格」，只用「建議優先看／可能有關／這次先不用看」。
 */
window.AidChat = (function () {
  const STUCK = '我卡住了';

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function init(container, opts) {
    opts = opts || {};
    const sid = 'web-' + Math.random().toString(36).slice(2);

    container.classList.add('aidchat');
    container.innerHTML =
      '<div class="aidchat-log" aria-live="polite"></div>' +
      '<div class="aidchat-inputbar">' +
        '<button class="aidchat-mic" type="button" aria-label="用說的" title="用說的">' +
          '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">' +
            '<path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z" fill="currentColor"/>' +
            '<path d="M5 11a7 7 0 0 0 14 0M12 18v3" stroke="currentColor" stroke-width="2" ' +
              'fill="none" stroke-linecap="round"/>' +
          '</svg>' +
        '</button>' +
        '<input class="aidchat-inp" placeholder="例：我的檨仔攏落了了" autocomplete="off" aria-label="輸入你的狀況">' +
        '<button class="aidchat-send">送出</button>' +
      '</div>';

    const log = container.querySelector('.aidchat-log');
    const inp = container.querySelector('.aidchat-inp');
    const sendBtn = container.querySelector('.aidchat-send');
    const micBtn = container.querySelector('.aidchat-mic');
    const demoToday = new URLSearchParams(window.location.search).get('demo')
      ? '2026-08-20' : null;

    function scrollBottom() { log.scrollTop = log.scrollHeight; }

    function addMsg(text, who) {
      const div = el('div', 'aidchat-msg ' + who);
      div.textContent = text;
      log.appendChild(div);
      scrollBottom();
      return div;
    }

    function clearOptions() {
      log.querySelectorAll('.aidchat-options').forEach(e => e.remove());
    }

    function addOptions(options) {
      clearOptions();
      if (!options || !options.length) return;
      const box = el('div', 'aidchat-options');
      options.forEach(opt => {
        const b = el('button', opt === STUCK ? 'aidchat-opt stuck' : 'aidchat-opt');
        b.textContent = opt;
        b.onclick = () => send(opt);
        box.appendChild(b);
      });
      log.appendChild(box);
      scrollBottom();
    }

    /* ---- 結果三層卡片 ---- */
    function chipHtml(card) {
      if (card.days_left != null) {
        return '<span class="rc-chip urgent">剩 ' + card.days_left + ' 天</span>';
      }
      if (card.window_type === '公告型' && card.window_note) {
        return '<span class="rc-chip normal">' + esc(card.window_note) + '</span>';
      }
      return '<span class="rc-chip normal">常態受理</span>';
    }

    // 只把推薦項目的識別資訊帶到 browser-only 表單頁；不帶 profile 或任何表單值。
    function applicationHref(card) {
      const params = new URLSearchParams();
      const programId = card.program_id || card.id || card.subsidy_id;
      if (programId) params.set('program_id', programId);
      if (card.variant_id) params.set('variant_id', card.variant_id);
      if (card.round_id) params.set('round_id', card.round_id);
      const template = card.form_template_id || (card.form_template && card.form_template.id);
      if (template) params.set('template_id', template);
      if (card.name) params.set('program_name', card.name);
      const query = params.toString();
      return 'form.html' + (query ? '?' + query : '');
    }

    function hasBrowserOfficialTemplate(card) {
      const template = card.form_template_id || (card.form_template && card.form_template.id);
      return template === 'farm_machine_115.labor_saving' ||
        template === 'farm_machine_115.electric_replacement';
    }

    function cardHtml(card, tier) {
      let h = '<article class="rc-card ' + tier + '">';
      h += '<div class="rc-top"><h3 class="rc-title">' + esc(card.name) + '</h3>' + chipHtml(card) + '</div>';
      if (card.close) h += '<div class="rc-line">受理至 ' + esc(card.close) + '</div>';
      if (card.amount) h += '<div class="rc-line rc-amount">' + esc(card.amount) + '</div>';
      if (tier === 'priority' && card.documents && card.documents.length) {
        h += '<div class="rc-docs"><div class="rc-docs-head">要準備的文件</div>';
        card.documents.forEach(d => {
          h += '<label class="rc-doc"><input type="checkbox">' +
               '<span>' + esc(d.name) +
               (d.exempt ? '<em class="rc-exempt">免附（豁免條款，帶身分證件即可）</em>'
                         : (d.where ? '<em class="rc-where">' + esc(d.where) + '</em>' : '')) +
               '</span></label>';
        });
        h += '</div>';
      }
      if (tier === 'maybe' && card.missing && card.missing.length) {
        h += '<div class="rc-missing">還差沒確認：' + esc(card.missing.join('、')) +
             '<br>不確定完全沒關係——帶著文件直接去問承辦，會幫你確認。</div>';
      }
      if (card.why && tier !== 'priority') {
        h += '<div class="rc-line rc-why">' + esc(card.why) + '</div>';
      }
      if (card.tasks && card.tasks.length) {
        h += '<div class="rc-tasks"><div class="rc-docs-head">下一步</div><ul>';
        card.tasks.slice(0, 2).forEach(task => {
          h += '<li>' + esc(task.title || task.name || '整理申請資料') + '</li>';
        });
        h += '</ul></div>';
      }
      const officeLine = [card.agency, card.office].filter(Boolean).join('・');
      if (officeLine) h += '<div class="rc-office">' + esc(officeLine) + '</div>';
      h += '<a class="rc-tel rc-apply" href="' + esc(applicationHref(card)) + '">' +
           (hasBrowserOfficialTemplate(card) ? '準備官方表單' : '查看申請方式') + '</a>';
      if (card.tel) {
        h += '<a class="rc-tel" href="tel:' + esc(card.tel.replace(/[^\d+#-]/g, '')) + '">找承辦電話　' + esc(card.tel) + '</a>';
      }
      if (card.last_verified) h += '<div class="rc-fine">最後查核 ' + esc(card.last_verified) + '</div>';
      h += '</article>';
      return h;
    }

    function renderResults(payload) {
      // The response contains only the public MatchingProfile.  Keep it in a
      // separate browser key so the local form page can prefill matching
      // fields without putting any form/private value in a URL or request.
      if (payload.matching_profile && typeof payload.matching_profile === 'object') {
        try {
          localStorage.setItem('aidstation_matching_profile', JSON.stringify(payload.matching_profile));
        } catch (e) {}
      }
      const wrap = el('div', 'aidchat-results');
      let h = '';

      if (payload.you_said && payload.you_said.length) {
        h += '<div class="rc-said"><span class="rc-said-label">你剛剛說的狀況：</span>';
        payload.you_said.forEach(f => {
          h += '<span class="rc-said-chip">' + esc(f.label) + '：' + esc(f.value) + '</span>';
        });
        h += '<button class="rc-redo" type="button">講錯了，改一下</button></div>';
      }

      const t = payload.tiers || {};
      if (t.priority && t.priority.length) {
        h += '<div class="rc-tier-head priority">建議優先看</div>';
        t.priority.forEach(c => { h += cardHtml(c, 'priority'); });
      }
      if (t.maybe && t.maybe.length) {
        h += '<div class="rc-tier-head maybe">可能有關，再確認一下就知道</div>';
        t.maybe.forEach(c => { h += cardHtml(c, 'maybe'); });
      }
      if (t.skip && t.skip.length) {
        h += '<details class="rc-skip"><summary>另外 ' + t.skip.length +
             ' 筆這次先不用看（點開看原因）</summary>';
        t.skip.forEach(s => {
          h += '<div class="rc-skip-item"><span class="rc-skip-name">' + esc(s.name) + '</span>' +
               '<span class="rc-skip-why">' + esc(s.why) + '</span></div>';
        });
        h += '<div class="rc-skip-note">條件常有例外，不放心的話，打一通電話問承辦最準。</div></details>';
      }
      h += '<div class="rc-disclaimer">※ ' + esc(payload.disclaimer || '實際資格由承辦單位認定') + '</div>';

      wrap.innerHTML = h;
      const redo = wrap.querySelector('.rc-redo');
      if (redo) redo.onclick = reset;
      log.appendChild(wrap);
      scrollBottom();
    }

    /* ---- 公文白話卡 ---- */
    function renderDocCard(card) {
      const wrap = el('div', 'aidchat-results');
      let h = '<article class="rc-card priority">';
      h += '<div class="rc-top"><h3 class="rc-title">' + esc(card.conclusion || '公文白話整理') + '</h3></div>';
      const dl = card.deadline || {};
      const dlText = dl.calc || dl.text || dl.advice;
      if (dlText) h += '<div class="rc-deadline-box">' + esc(dlText) + '</div>';
      if (card.todo && card.todo.length) {
        h += '<div class="rc-docs"><div class="rc-docs-head">你要做的事</div>';
        card.todo.forEach(td => {
          h += '<label class="rc-doc"><input type="checkbox"><span>' + esc(td.item) +
               (td.where ? '<em class="rc-where">' + esc(td.where) + '</em>' : '') + '</span></label>';
        });
        h += '</div>';
      }
      if (card.consequence) h += '<div class="rc-missing">' + esc(card.consequence) + '</div>';
      h += '</article>';
      h += '<div class="rc-disclaimer">※ ' + esc(card.disclaimer || '翻譯僅供參考，日期不確定時請以電話向承辦確認。') + '</div>';
      wrap.innerHTML = h;
      log.appendChild(wrap);
      scrollBottom();
    }

    async function call(body) {
      const request = Object.assign({ session_id: sid }, body);
      if (demoToday) request.today = demoToday;
      const r = await fetch('/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(request)
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }

    function handleReply(data) {
      if (data.payload && data.payload.kind === 'results') {
        addMsg('幫你整理好了，往下看：', 'bot');
        renderResults(data.payload);
        addOptions(data.options);
      } else if (data.payload && data.payload.kind === 'doc_card') {
        renderDocCard(data.payload.card);
        addOptions(data.options);
      } else {
        addMsg(data.text, 'bot');
        addOptions(data.options);
      }
    }

    async function send(text, kind, extra) {
      text = (text || '').trim();
      if (!text && !extra) return;
      addMsg(text || '（我傳了一張公文照片）', 'user');
      clearOptions();
      const typing = addMsg(kind === 'document_image' ? '照片收到了，正在看…' : '…', 'bot');
      try {
        const data = await call(Object.assign({ text: text, kind: kind || 'text' }, extra));
        typing.remove();
        handleReply(data);
      } catch (err) {
        typing.remove();
        if (location.protocol === 'file:') {
          addMsg('這個頁面是直接開檔案的，連不到後端。\n請先啟動程式（python run.py），再用瀏覽器開 http://localhost:8000/app/', 'bot');
        } else {
          addMsg('連不上伺服器（' + err.message + '）。\n請確認 python run.py 有在跑，再重新整理試試。', 'bot');
        }
      }
    }

    async function reset() {
      log.innerHTML = '';
      try {
        const data = await call({ kind: 'reset' });
        addMsg(data.text, 'bot');
      } catch (err) {
        addMsg('你好！跟我說發生什麼事，講一句話就好（例：我的檨仔攏落了了）。', 'bot');
      }
      if (opts.starters) addOptions(opts.starters);
    }

    sendBtn.onclick = () => { const t = inp.value; inp.value = ''; send(t); };
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') { const t = inp.value; inp.value = ''; send(t); }
    });

    /* ---- 語音輸入（華語）----------------------------------------------
       依《系統設計建議書》§3.3：
       - 語音是輔助，不是唯一路徑：打字與按鈕永遠都在
       - 辨識結果先放進輸入框讓使用者確認，不自動送出（先覆誦再送）
       - 辨識失敗不卡死流程，只提示改用打字
       瀏覽器內建的辨識只支援華語；台語要另外接 ASR 服務（見 README）。 */
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recog = null, listening = false;

    function micUnavailable(reason) {
      micBtn.disabled = true;
      micBtn.classList.add('off');
      micBtn.title = reason;
      micBtn.setAttribute('aria-label', reason);
    }

    if (!SR) {
      micUnavailable('這個瀏覽器不支援語音輸入，請用打字的');
    } else if (!window.isSecureContext) {
      // http 的區域網路位址不算安全來源，瀏覽器不給用麥克風
      micUnavailable('語音輸入需要 https 才能用，請用打字的');
    } else {
      micBtn.onclick = () => {
        if (listening) { recog && recog.stop(); return; }
        recog = new SR();
        recog.lang = 'zh-TW';
        recog.interimResults = true;
        recog.continuous = false;

        recog.onstart = () => {
          listening = true;
          micBtn.classList.add('on');
          inp.placeholder = '請說話…說完會停下來讓你確認';
        };
        recog.onresult = e => {
          let text = '';
          for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
          inp.value = text;                 // 只填進去，不自動送出
        };
        recog.onerror = e => {
          const why = e.error === 'not-allowed'
            ? '沒有麥克風權限，請在網址列左邊允許麥克風，或直接用打字的'
            : e.error === 'no-speech'
              ? '沒有聽到聲音，再試一次或用打字的'
              : '語音辨識沒有成功，用打字的也可以';
          addMsg(why, 'bot');
        };
        recog.onend = () => {
          listening = false;
          micBtn.classList.remove('on');
          inp.placeholder = '例：我的檨仔攏落了了';
          if (inp.value.trim()) {
            addMsg('我聽到的是：「' + inp.value.trim() + '」\n對的話按送出，不對可以直接改。', 'bot');
            inp.focus();
          }
        };
        try { recog.start(); } catch (e) { /* 連按兩下會丟錯，忽略 */ }
      };
    }

    // 開場
    addMsg(opts.greeting ||
      '你好！我是農民補給站。\n遇到災損、想查補助，用一句話告訴我就好，台語嘛通。', 'bot');
    if (opts.starters) addOptions(opts.starters);

    return {
      send, reset,
      sendDocument: (text) => send(text, 'document'),
      sendDocumentImage: (dataUrl) => send('', 'document_image', { image: dataUrl })
    };
  }

  return { init };
})();
