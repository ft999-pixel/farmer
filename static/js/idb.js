const IDB = (() => {
  const DB_NAME = 'FormPrefill';
  const DB_VERSION = 1;

  function open() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('profiles')) {
          db.createObjectStore('profiles', { keyPath: 'key' });
        }
        if (!db.objectStoreNames.contains('applications')) {
          const s = db.createObjectStore('applications', { keyPath: 'id' });
          s.createIndex('template_version_id', 'template_version_id');
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function tx(store, mode = 'readonly') {
    return open().then(db => db.transaction(store, mode).objectStore(store));
  }

  function get(store, key) {
    return tx(store).then(s => new Promise((res, rej) => {
      const r = s.get(key);
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    }));
  }

  function put(store, value) {
    return tx(store, 'readwrite').then(s => new Promise((res, rej) => {
      const r = s.put(value);
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    }));
  }

  function getAll(store) {
    return tx(store).then(s => new Promise((res, rej) => {
      const r = s.getAll();
      r.onsuccess = () => res(r.result || []);
      r.onerror = () => rej(r.error);
    }));
  }

  return { get, put, getAll };
})();
