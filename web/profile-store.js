/*
 * Browser-only storage for PrivateFormProfile.
 *
 * Keep this file deliberately independent from the API client.  A caller can
 * only save the allow-listed private form fields, and this module never calls
 * fetch (or any other network API).
 */
(function (root, factory) {
  const store = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = store;
  else root.ProfileStore = store;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  const STORAGE_KEY = 'aidstation_private_form_profile_v1';
  const VERSION = 1;

  // Aliases are accepted when importing a value, but only canonical keys are
  // written back to storage.  This also makes old form field names harmless.
  const ALIASES = Object.freeze({
    full_name: ['full_name', 'name'],
    national_id: ['national_id', 'id_number'],
    birthday: ['birthday', 'birth_date', 'birth_year'],
    phone: ['phone', 'tel', 'mobile'],
    full_address: ['full_address', 'address', 'addr'],
    bank_account: ['bank_account'],
    bank_branch: ['bank_branch'],
    parcel_numbers: ['parcel_numbers', 'parcel_number'],
    signature: ['signature', 'applicant_signature'],
  });

  const PRIVATE_KEYS = Object.freeze(
    [...new Set(Object.values(ALIASES).flat())]
  );
  const PRIVATE_KEY_SET = new Set(PRIVATE_KEYS);

  function keyName(key) {
    return String(key || '')
      .replace(/([a-z])([A-Z])/g, '$1_$2')
      .replace(/[\s-]+/g, '_')
      .toLowerCase();
  }

  function isPrivateKey(key) {
    const normalized = keyName(key);
    return PRIVATE_KEY_SET.has(normalized) ||
      normalized === 'contact' ||
      normalized === 'contacts' ||
      normalized === 'private' ||
      normalized === 'private_profile' ||
      normalized === 'private_form_profile' ||
      normalized === 'privateformprofile';
  }

  function cloneValue(value) {
    if (Array.isArray(value)) return value.map(cloneValue);
    if (value && typeof value === 'object') {
      const result = {};
      Object.entries(value).forEach(([key, child]) => {
        // PrivateFormProfile is flat by design.  Do not retain a nested
        // contact/private object even if a caller passes one accidentally.
        if (!isPrivateKey(key) || PRIVATE_KEY_SET.has(keyName(key))) {
          result[key] = cloneValue(child);
        }
      });
      return result;
    }
    return value;
  }

  function firstValue(source, keys) {
    for (const key of keys) {
      if (Object.prototype.hasOwnProperty.call(source, key)) {
        const value = source[key];
        if (value !== undefined && value !== null && value !== '') return value;
      }
    }
    return undefined;
  }

  function normalize(input) {
    const source = input && typeof input === 'object' && !Array.isArray(input)
      ? input : {};
    const result = {};
    Object.entries(ALIASES).forEach(([canonical, aliases]) => {
      const value = firstValue(source, aliases);
      if (value === undefined) return;
      if (canonical === 'parcel_numbers') {
        const values = Array.isArray(value)
          ? value
          : String(value).split(/[\n,，、]+/);
        const cleaned = values.map(x => String(x).trim()).filter(Boolean);
        if (cleaned.length) result[canonical] = cleaned;
      } else {
        const text = typeof value === 'string' ? value.trim() : value;
        if (text !== '') result[canonical] = cloneValue(text);
      }
    });
    return result;
  }

  function getStorage() {
    try {
      return root && root.localStorage ? root.localStorage : null;
    } catch (e) {
      return null;
    }
  }

  function load() {
    const storage = getStorage();
    if (!storage) return {};
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      // Accept a plain object as a small migration path from early demos;
      // future writes always use the versioned envelope.
      return normalize(parsed && parsed.profile ? parsed.profile : parsed);
    } catch (e) {
      return {};
    }
  }

  function save(input) {
    const profile = normalize(input);
    const storage = getStorage();
    if (!storage) throw new Error('本機儲存功能目前無法使用');
    storage.setItem(STORAGE_KEY, JSON.stringify({
      version: VERSION,
      profile,
      updated_at: new Date().toISOString(),
    }));
    return profile;
  }

  function clear() {
    const storage = getStorage();
    if (storage) storage.removeItem(STORAGE_KEY);
  }

  function hasData() {
    return Object.keys(load()).length > 0;
  }

  return Object.freeze({
    STORAGE_KEY,
    VERSION,
    PRIVATE_KEYS,
    isPrivateKey,
    normalize,
    load,
    save,
    clear,
    hasData,
    storageKind: 'localStorage',
  });
});
