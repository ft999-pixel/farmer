/*
 * 資料要不要留在這台裝置，由「有沒有註冊」決定。
 *
 *   沒註冊 → sessionStorage：這一趟用得好好的（查補助、預填、列印都正常），
 *            但關掉分頁就沒了，硬碟上不留任何東西。
 *   註冊了 → localStorage：下次打開還在，換裝置也帶得走（媒合資料存在帳號上）。
 *
 * 為什麼不是「匿名就完全不存」：預填表單在另一個頁面（form.html），
 * 頁面之間本來就得有地方交接資料。sessionStorage 正是為這件事存在的——
 * 它撐得過跳頁，但撐不過關掉瀏覽器。
 *
 * 開關本身（aidstation_persist）放在 localStorage，值只有 '1'，
 * 不含任何個人資料；它只回答「這台瀏覽器有沒有登入中的使用者」。
 * profile.html 問過 /members/me 之後負責校正它。
 */
(function (root) {
  'use strict';

  const FLAG_KEY = 'aidstation_persist';

  // 切換模式時要搬家的鍵。刻意用前綴比對而不是寫死清單——各個 store 的鍵名帶
  // 版本後綴（例如 aidstation_applications_v1），寫死過一次就漏過一次，
  // 症狀是「註冊之後申請進度不見了」，而且要等到有人真的註冊才會發現。
  const KEY_PREFIX = 'aidstation_';

  function migratableKeys(store) {
    const keys = [];
    try {
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i);
        if (key && key.indexOf(KEY_PREFIX) === 0 && key !== FLAG_KEY) keys.push(key);
      }
    } catch (e) { /* 無法列舉就當作沒有東西要搬 */ }
    return keys;
  }

  function safe(getter) {
    try { return getter(); } catch (e) { return null; }
  }

  const local = () => safe(() => root.localStorage);
  const session = () => safe(() => root.sessionStorage);

  function isPersistent() {
    const store = local();
    if (!store) return false;
    try { return store.getItem(FLAG_KEY) === '1'; } catch (e) { return false; }
  }

  /** 目前該用哪一個儲存區。所有 aidstation_* 的讀寫都要走這裡。 */
  function area() {
    return isPersistent() ? (local() || session()) : (session() || local());
  }

  function move(from, to) {
    if (!from || !to || from === to) return;
    migratableKeys(from).forEach(function (key) {
      try {
        const value = from.getItem(key);
        if (value !== null) to.setItem(key, value);
        from.removeItem(key);
      } catch (e) { /* 配額滿或被限制時，至少不要中斷整個流程 */ }
    });
  }

  /**
   * 登入狀態變了就呼叫一次。
   * 註冊／登入 → 把這一趟填的東西搬進 localStorage，讓它留下來。
   * 登出       → 反向搬回 sessionStorage，硬碟上不留東西。
   */
  function setPersistent(on) {
    const store = local();
    if (!store) return false;
    const want = Boolean(on);
    if (want === isPersistent()) return want;
    try {
      if (want) {
        store.setItem(FLAG_KEY, '1');
        move(session(), store);
      } else {
        store.removeItem(FLAG_KEY);
        move(store, session());
      }
    } catch (e) {
      return isPersistent();
    }
    return want;
  }

  root.AidStorage = Object.freeze({
    FLAG_KEY: FLAG_KEY,
    KEY_PREFIX: KEY_PREFIX,
    area: area,
    isPersistent: isPersistent,
    setPersistent: setPersistent
  });
})(typeof globalThis !== 'undefined' ? globalThis : this);
