(() => {
  const host = document.querySelector('[data-site-nav]');
  if (!host) return;

  const page = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  const params = new URLSearchParams(location.search);
  const hash = location.hash.toLowerCase();
  const isAdmin = host.dataset.siteNav === 'admin' || page === 'admin.html';
  const banner = document.querySelector('.demo-banner');
  if (banner) {
    host.classList.add('site-nav-host--banner');
    host.style.setProperty('--site-nav-banner-height', `${banner.getBoundingClientRect().height}px`);
  }

  const links = [
    ['browse', 'browse.html', '找補助'],
    ['doc', 'chat.html?tab=doc', '看懂公文'],
    ['guides', 'index.html#guides', '白話指南'],
    ['profile', 'profile.html', '我的資料'],
    ['dashboard', 'dashboard.html', '卡點儀表板'],
    ['about', 'index.html#about', '關於']
  ];

  function activeKey() {
    if (isAdmin) return 'admin';
    if (page === 'browse.html' || page === 'program.html') return 'browse';
    if (page === 'chat.html') return params.get('tab') === 'doc' ? 'doc' : '';
    if (page === 'guide.html') return 'guides';
    if (page === 'profile.html') return 'profile';
    if (page === 'dashboard.html') return 'dashboard';
    if (page === 'index.html' || page === '') {
      if (hash.startsWith('#guides')) return 'guides';
      if (hash.startsWith('#about')) return 'about';
    }
    return '';
  }

  const current = activeKey();
  const ctaHref = page === 'index.html' || page === '' ? '#talk' : 'chat.html';
  const linkMarkup = links.map(([key, href, label]) => {
    const isCurrent = key === current;
    const kind = key === 'doc' ? 'doc' : key === 'about' ? 'about' : '';
    const hint = key === 'doc' ? '拍照或貼上公文，翻成白話' : key === 'about' ? '了解本站、資料來源與使用方式' : '';
    const classes = ['site-nav__link', kind ? `site-nav__link--${kind}` : '', isCurrent ? 'current' : '']
      .filter(Boolean).join(' ');
    const extra = [
      isCurrent ? 'aria-current="page"' : '',
      kind ? `data-nav-kind="${kind}"` : '',
      key === 'about' ? 'data-nav-about' : '',
      hint ? `data-nav-hint="${hint}" title="${hint}"` : ''
    ].filter(Boolean).join(' ');
    return `<a href="${href}" class="${classes}"${extra ? ` ${extra}` : ''}>${label}</a>`;
  }).join('');
  const adminMarkup = isAdmin
    ? '<a href="admin.html" class="current" aria-current="page">資料維護</a>'
    : '';
  const ctaCurrent = page === 'chat.html' && params.get('tab') !== 'doc';
  const logoutMarkup = isAdmin ? '<button id="logout" class="site-nav__logout hide" type="button">登出</button>' : '';

  host.innerHTML = `
    <div class="site-nav-wrap">
      <nav class="site-nav" aria-label="主要導覽">
        <a href="index.html" class="site-nav__logo" aria-label="農民補給站首頁">
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
            <path d="M4 2v18" stroke="#06301F" stroke-width="2.5" stroke-linecap="round"/>
            <path d="M4 3L18 7L4 11Z" fill="#02DF82"/>
          </svg>
          農民補給站
        </a>
        <div class="site-nav__links">${linkMarkup}${adminMarkup}</div>
        <div class="site-nav__tools">
          <div class="site-nav__font" role="group" aria-label="字級切換">
            <button type="button" data-site-font="小">小</button>
            <button type="button" data-site-font="中">中</button>
            <button type="button" data-site-font="大">大</button>
          </div>
          <a href="${ctaHref}" class="site-nav__cta${ctaCurrent ? ' current' : ''}"${ctaCurrent ? ' aria-current="page"' : ''}>說說你的狀況</a>
          ${logoutMarkup}
        </div>
      </nav>
    </div>`;

  const fontButtons = host.querySelectorAll('[data-site-font]');
  const fontSizes = { '小': '15px', '中': '16px', '大': '19px' };
  function applyFontSize(value) {
    document.documentElement.style.fontSize = fontSizes[value];
    fontButtons.forEach(button => button.classList.toggle('active', button.dataset.siteFont === value));
  }

  let saved = localStorage.getItem('aid-fs');
  if (!fontSizes[saved]) saved = '中';
  applyFontSize(saved);
  fontButtons.forEach(button => button.addEventListener('click', () => {
    localStorage.setItem('aid-fs', button.dataset.siteFont);
    applyFontSize(button.dataset.siteFont);
  }));

  const navWrap = host.querySelector('.site-nav-wrap');
  function syncNavSpace() {
    const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
    if (banner) host.style.setProperty('--site-nav-banner-height', `${bannerHeight}px`);
    if (navWrap) {
      const navTop = parseFloat(getComputedStyle(navWrap).top) || 0;
      const relativeTop = Math.max(0, navTop - bannerHeight);
      host.style.minHeight = `${Math.ceil(navWrap.getBoundingClientRect().height + relativeTop)}px`;
    }
  }
  syncNavSpace();
  if (window.ResizeObserver && navWrap) new ResizeObserver(syncNavSpace).observe(navWrap);
  window.addEventListener('resize', syncNavSpace);

  function updateScrollState() {
    host.classList.toggle('is-scrolled', window.scrollY > 8);
  }
  updateScrollState();
  window.addEventListener('scroll', updateScrollState, {passive: true});

  const aboutLink = host.querySelector('[data-nav-about]');
  if (aboutLink && typeof HTMLDialogElement !== 'undefined' && HTMLDialogElement.prototype.showModal) {
    const dialog = document.createElement('dialog');
    dialog.className = 'site-about-dialog';
    dialog.setAttribute('aria-labelledby', 'site-about-title');
    dialog.innerHTML = `
      <div class="site-about-dialog__inner">
        <button class="site-about-dialog__close" type="button" aria-label="關閉關於本站">×</button>
        <p class="site-about-dialog__eyebrow">關於農民補給站</p>
        <h2 id="site-about-title">把補助說清楚，陪你把事情辦好</h2>
        <p>這是一個協助農民找補助、看懂公文與準備申請資料的示範原型。</p>
        <div class="site-about-dialog__points">
          <div class="site-about-dialog__point"><b>來源清楚</b><br>每筆補助都附來源與查核日期。</div>
          <div class="site-about-dialog__point"><b>先理解再申請</b><br>白話說明只幫助理解，實際資格仍以承辦單位認定為準。</div>
          <div class="site-about-dialog__point"><b>不用有壓力</b><br>免費、不代辦、不用註冊也能先查補助。</div>
        </div>
        <a class="site-about-dialog__link" href="index.html#about">看完整的本站說明</a>
      </div>`;
    document.body.appendChild(dialog);

    let lastFocused = null;
    function closeAbout() {
      if (dialog.open) dialog.close();
      if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
    }
    aboutLink.addEventListener('click', event => {
      event.preventDefault();
      lastFocused = document.activeElement;
      dialog.showModal();
      dialog.querySelector('.site-about-dialog__close').focus();
    });
    dialog.querySelector('.site-about-dialog__close').addEventListener('click', closeAbout);
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      closeAbout();
    });
    dialog.addEventListener('click', event => {
      if (event.target === dialog) closeAbout();
    });
  }
})();
