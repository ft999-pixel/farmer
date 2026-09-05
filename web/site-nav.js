/* 導覽列依登入狀態調整。九個頁面共用這一份，不各寫一次。
 *
 * 未登入      ：隱藏「我的資料」，顯示「登入」
 * 農民登入後  ：顯示「我的資料」，「登入」變「登出」
 * 承辦登入後  ：另外顯示「資料維護」，「登入」變「登出」
 *
 * 「我的資料」是登入後才有的頁面，所以未登入時不該出現在導覽列。
 * 真正的門檔在 profile.html 自己（見該頁的 requireLogin），
 * 這裡只負責畫面，不能當成權限控制。
 */
(function () {
  const nav = document.querySelector('.nav-links');
  if (!nav) return;

  const byHref = (needle) =>
    [...nav.querySelectorAll('a')].find(a => (a.getAttribute('href') || '').startsWith(needle));

  const profileLink = byHref('profile.html');
  const loginLink = byHref('login.html');

  // 預設先把「我的資料」藏起來，確認登入後再顯示，避免閃一下又消失
  if (profileLink) profileLink.style.display = 'none';

  fetch('/auth/me', { credentials: 'same-origin' })
    .then(r => r.json())
    .then(me => {
      if (!me.logged_in) return;

      if (profileLink && me.role === 'member') profileLink.style.display = '';

      // 承辦人員多一個後臺入口
      if (me.role === 'admin' && !byHref('admin.html')) {
        const a = document.createElement('a');
        a.href = 'admin.html';
        a.textContent = '資料維護';
        nav.insertBefore(a, loginLink || null);
      }

      if (loginLink) {
        loginLink.textContent = '登出';
        loginLink.href = '#';
        loginLink.onclick = async (e) => {
          e.preventDefault();
          await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
          location.href = 'index.html';
        };
      }
    })
    .catch(() => { /* 後端不通時維持預設樣子，不擋住頁面 */ });
})();
