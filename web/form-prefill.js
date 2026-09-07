/*
 * 農民補給站 browser-only Form Prefill
 *
 * The official PDF is always the visual source of truth.  This file only
 * reads localStorage, renders editable HTML controls over the PDF, and keeps
 * print-only text spans at the coordinates in data/form_templates.json.  It
 * does not submit form values to a server.
 */
(function (root, doc) {
  'use strict';

  const PDF_WIDTH = 595.32;
  const PDF_HEIGHT = 841.92;
  const DEFAULT_TEMPLATE_ID = 'farm_machine_115.labor_saving';

  const STORAGE_KEYS = Object.freeze({
    matching: 'aidstation_matching_profile',
    privateForm: 'aidstation_private_form_profile',
    drafts: 'aidstation_form_drafts',
    tasks: 'aidstation_task_progress'
  });

  // Worker B may use one of these equivalent names while the demo evolves.
  // All candidates are browser storage keys; none are network sources.
  const STORAGE_ALIASES = Object.freeze({
    matching: [
      STORAGE_KEYS.matching,
      'aidstation_matchingProfile',
      'matchingProfile',
      'MatchingProfile',
      'aidstation_profile_matching',
      'aidstation_profile'
    ],
    privateForm: [
      STORAGE_KEYS.privateForm,
      'aidstation_private_form_profile_v1',
      'aidstation_privateFormProfile',
      'privateFormProfile',
      'PrivateFormProfile',
      'aidstation_private_profile',
      'aidstation_profile'
    ]
  });

  const PRIVATE_ALIASES = Object.freeze({
    full_name: ['full_name', 'name', 'applicant_name', '姓名'],
    phone: ['phone', 'mobile', 'tel', '電話', '聯絡電話'],
    national_id: ['national_id', 'id_number', 'idNumber', '身分證', '身分證字號'],
    birth_year: ['birth_year', 'birth_year_roc', 'birthday', 'birth_date', 'birthYear', '出生年份'],
    full_address: ['full_address', 'address', 'addr', 'registered_address', '通訊地址', '地址'],
    landline: ['landline', 'tel', 'phone', '電話'],
    // 地號指得出是哪一塊地、是誰的，跟姓名同級。受災證明書把它拆成
    // 座落區段／地號／持分三欄，三欄都留在本機，不進 MatchingProfile。
    parcel_numbers: ['parcel_numbers', 'parcel_number', 'land_number', '地號'],
    land_section: ['land_section', 'land_lot', '地段', '受災土地座落區段'],
    land_share: ['land_share', '持分']
  });

  const MATCHING_ALIASES = Object.freeze({
    crops: ['crops', 'crop', '作物', '種植作物種類'],
    qualification: [
      'qualification',
      'qualifications',
      'technical_qualification',
      'certifications',
      'entry_criteria',
      '申請資格'
    ],
    location: ['location', 'township', 'region', '耕作地區', '鄉鎮'],
    land_area_ha: ['land_area_ha', 'land_area', 'area_ha', '面積'],
    intent: ['intent', 'equipment_intent', '申請意圖'],
    machine_type: ['machine_type', 'equipment_type', '農機機種'],
    machine_model: ['machine_model', 'model', 'equipment_model', '規格或牌型'],
    score_items: ['score_items', 'score_codes', '配分項目'],
    total_score: ['total_score', '總分'],
    old_machine_cert_no: ['old_machine_cert_no', 'old_machine_certificate', '預計報廢農機證號'],
    expected_delivery_date: ['expected_delivery_date', 'delivery_date', '預計交貨日期'],
    // 受災證明書。災害名稱要填公告上的名字（例如「凱米颱風」），
    // 所以不從 facts.event（只會是「天然災害」）帶入，寧可留白。
    disaster_name: ['disaster_name', 'disaster', '災害名稱'],
    apply_year: ['apply_year', '申請年'],
    apply_month: ['apply_month', '申請月'],
    apply_day: ['apply_day', '申請日']
  });

  const FALLBACK_TASKS = [
    {
      id: 'confirm-documents',
      title: '確認推薦卡上的應備文件',
      description: '把手邊已有的文件先整理好，缺的到現場向承辦確認。',
      depends_on: []
    },
    {
      id: 'confirm-qualification',
      title: '補充申請資格說明',
      description: '把作物、用途和已經知道的條件先整理好；實際資格還是由承辦單位認定。',
      depends_on: []
    },
    {
      id: 'complete-local-form',
      title: '檢查填好的資料',
      description: '確認資料正確，缺的欄位可以直接修改或留白。',
      depends_on: ['confirm-documents']
    },
    {
      id: 'ask-authority',
      title: '預覽、列印並洽承辦',
      description: '帶著官方表單與文件到推薦卡上的農會、公所或承辦單位。',
      depends_on: ['complete-local-form']
    }
  ];

  const SHARED_PRIVATE_FIELDS = [
    {
      field_key: 'applicant_name', label: '姓名', type: 'text',
      pos_x: 171, pos_y: 594, width: 137, height: 14,
      required: true, editable: true, prefill_source: 'private.full_name',
      storage_scope: 'private', autocomplete: 'name'
    },
    {
      field_key: 'phone', label: '電話', type: 'text',
      pos_x: 410, pos_y: 594, width: 110, height: 14,
      required: true, editable: true, prefill_source: 'private.phone',
      storage_scope: 'private', autocomplete: 'tel'
    },
    {
      field_key: 'national_id', label: '身分證統一編號', type: 'text',
      pos_x: 171, pos_y: 574, width: 137, height: 13,
      required: true, editable: true, prefill_source: 'private.national_id',
      storage_scope: 'private', autocomplete: 'off'
    },
    {
      field_key: 'birth_year', label: '出生年份', type: 'text',
      pos_x: 445, pos_y: 574, width: 46, height: 13,
      required: true, editable: true, prefill_source: 'private.birth_year',
      storage_scope: 'private', inputmode: 'numeric'
    },
    {
      field_key: 'address', label: '地址', type: 'text',
      pos_x: 171, pos_y: 553, width: 230, height: 14,
      required: true, editable: true, prefill_source: 'private.full_address',
      storage_scope: 'private', autocomplete: 'street-address'
    },
    {
      field_key: 'crop', label: '種植作物種類', type: 'text',
      pos_x: 473, pos_y: 553, width: 48, height: 14,
      required: false, editable: true, prefill_source: 'matching.crops',
      storage_scope: 'matching'
    }
  ];

  function field(fieldKey, label, type, x, y, width, height, source, required) {
    return {
      field_key: fieldKey, label: label, type: type,
      pos_x: x, pos_y: y, width: width, height: height,
      required: Boolean(required), editable: true,
      prefill_source: source, storage_scope: 'matching'
    };
  }

  function privateField(fieldKey, label, x, y, width, height, source, autocomplete, required) {
    return {
      field_key: fieldKey, label: label, type: 'text',
      pos_x: x, pos_y: y, width: width, height: height,
      required: required !== false, editable: true,
      prefill_source: source, storage_scope: 'private',
      autocomplete: autocomplete || 'off'
    };
  }

  // 沒有 storage_scope：值只留在這張表的草稿，不寫進 MatchingProfile 也不寫進本機個資。
  function draftField(fieldKey, label, x, y, width, height, source, note) {
    return {
      field_key: fieldKey, label: label, type: 'text',
      pos_x: x, pos_y: y, width: width, height: height,
      required: true, editable: true,
      prefill_source: source || '', note: note || ''
    };
  }

  function helperQualification(note) {
    return {
      field_key: 'qualification',
      label: '申請資格說明（輔助備註）',
      type: 'textarea',
      required: false,
      editable: true,
      prefill_source: 'matching.qualification',
      storage_scope: 'matching',
      helper_only: true,
      overlay: false,
      note: note
    };
  }

  const OFFICIAL_TEMPLATES = [
    {
      id: 'farm_machine_115.labor_saving',
      name: '115年省工農業機械／新研發農機補助申請書',
      program: '115年省工高效及碳匯農機補助實施計畫',
      attachment: '附表9',
      official_source_page: 36,
      official_pdf: 'futuremode_official_forms_v2/pdfs/labor_saving.pdf',
      pdf_url: '/official-forms/pdf/labor_saving.pdf',
      preview_image: '/app/official-forms/labor_saving.png',
      web_pdf: 'official-forms/labor_saving.pdf',
      official_layout: true,
      program_ids: ['farm-machine-115', 'afa115-appendix-09', 'afa-farm-machinery'],
      tasks: [
        { id: 'confirm-documents', title: '確認附表9與應備文件', description: '對照推薦卡的文件清單，整理好申請書、身分證件及承辦要求的附件。', depends_on: [] },
        { id: 'confirm-qualification', title: '補充申請資格說明', description: '把作物、農機用途與已知的驗證或資格資訊整理在旁邊；實際資格仍由承辦單位認定。', depends_on: [] },
        { id: 'complete-local-form', title: '檢查預填內容', description: '確認姓名、電話、身分證、出生年份、地址這些有沒有填對。', depends_on: ['confirm-documents'] },
        { id: 'print-and-visit', title: '預覽、列印並洽承辦', description: '列印官方附表9，帶著文件到推薦卡上的農會、公所或承辦單位確認。', depends_on: ['complete-local-form'] }
      ],
      fields: SHARED_PRIVATE_FIELDS.concat([
        field('machine_type', '農機機種', 'text', 235, 449, 165, 18, 'matching.machine_type', true),
        field('machine_model', '規格或牌型', 'text', 445, 449, 76, 18, 'matching.machine_model', true),
        field('score_items', '配分項目', 'text', 171, 362, 137, 23, 'matching.score_items', false),
        field('total_score', '總分', 'number', 346, 362, 54, 23, 'matching.total_score', false),
        field('expected_delivery_date', '預計交貨日期', 'text', 171, 274, 124, 13, 'matching.expected_delivery_date', false),
        helperQualification('這是旁邊的整理欄，不是官方附表9欄位，不會畫到政府表單。')
      ])
    },
    {
      id: 'farm_machine_115.electric_replacement',
      name: '115年汰舊燃油農機換購電動農機補助申請書',
      program: '115年省工高效及碳匯農機補助實施計畫',
      attachment: '附表16',
      official_source_page: 43,
      official_pdf: 'futuremode_official_forms_v2/pdfs/electric_replacement.pdf',
      pdf_url: '/official-forms/pdf/electric_replacement.pdf',
      preview_image: '/app/official-forms/electric_replacement.png',
      web_pdf: 'official-forms/electric_replacement.pdf',
      official_layout: true,
      program_ids: ['farm-machine-115.electric-replacement', 'electric-replacement', 'afa115-appendix-16'],
      tasks: [
        { id: 'confirm-old-machine', title: '確認汰舊農機資料', description: '找出預計報廢燃油農機的證號或承辦要求的證明文件。', depends_on: [] },
        { id: 'confirm-qualification', title: '補充申請資格說明', description: '把作物、換購用途與已知的資格資訊整理在旁邊；實際資格仍由承辦單位認定。', depends_on: [] },
        { id: 'complete-local-form', title: '檢查預填內容', description: '確認姓名、電話、身分證、出生年份、地址這些有沒有填對。', depends_on: ['confirm-old-machine'] },
        { id: 'print-and-visit', title: '預覽、列印並洽承辦', description: '列印官方附表16，帶著文件到推薦卡上的農會、公所或承辦單位確認。', depends_on: ['complete-local-form'] }
      ],
      fields: SHARED_PRIVATE_FIELDS.concat([
        field('machine_type', '農機機種', 'text', 235, 453, 165, 18, 'matching.machine_type', true),
        field('machine_model', '規格或牌型', 'text', 445, 453, 76, 18, 'matching.machine_model', true),
        field('old_machine_cert_no', '預計報廢農機證號', 'text', 90, 398, 99, 15, 'matching.old_machine_cert_no', true),
        field('expected_delivery_date', '預計交貨日期', 'text', 171, 297, 124, 13, 'matching.expected_delivery_date', false),
        helperQualification('這是旁邊的整理欄，不是官方附表16欄位，不會畫到政府表單。')
      ])
    },
    {
      // 座標取自官方 PDF 的表格線（垂直線 x=33.8/109.7/234.9/345.7/389.4/423.6/553，
      // 水平線 y=730.3/710.0/689.9/669.6/635.4/615.1），只疊「一、基本資料」。
      // 「二、實地調查損失情形」是調查人員填的，一格都不碰。
      id: 'disaster_cash.damage_certificate',
      name: '農業天然災害受災證明書',
      program: '農業天然災害現金救助',
      attachment: '附件1',
      official_source_page: 1,
      official_pdf: 'web/official-forms/disaster_certificate.pdf',
      pdf_url: '/official-forms/pdf/disaster_certificate.pdf',
      preview_image: '/app/official-forms/disaster_certificate.png',
      web_pdf: 'official-forms/disaster_certificate.pdf',
      official_layout: true,
      program_ids: ['moa-disaster-cash-sample-2026', 'disaster-cash-sample'],
      tasks: [
        { id: 'photo-before-cleanup', title: '先拍照，再整理田地', description: '田一旦清理過就證明不了當初的損失。用農業部「農損拍照 APP」拍會自動記錄時間和位置。', depends_on: [] },
        { id: 'confirm-announcement', title: '打電話確認公告範圍', description: '問公所農業課：你的鄉鎮和你種的作物，有沒有在這次公告的救助地區與品項裡。', depends_on: [] },
        { id: 'complete-local-form', title: '檢查預填內容', description: '確認災害名稱、申請日期、姓名、身分證、住址、電話與土地地號填對了。', depends_on: ['confirm-announcement'] },
        { id: 'print-and-visit', title: '列印並到公所農業課', description: '列印受災證明書，連同身分證、印章、存摺封面影本、土地文件與災損照片一起帶去。', depends_on: ['complete-local-form'] }
      ],
      fields: [
        draftField('disaster_name', '災害名稱', 113, 713, 228, 15, '', '公告上寫的名字，例如「凱米颱風」。'),
        draftField('apply_year', '申請日期（民國年）', 429, 713, 36, 15, 'today.year'),
        draftField('apply_month', '申請月份', 486, 713, 16, 15, 'today.month'),
        draftField('apply_day', '申請日', 521, 713, 16, 15, 'today.day'),
        privateField('applicant_name', '申請人姓名', 113, 693, 228, 15, 'private.full_name', 'name'),
        privateField('national_id', '身分證字號', 429, 693, 120, 15, 'private.national_id', 'off'),
        privateField('address', '住址', 113, 673, 228, 15, 'private.full_address', 'street-address'),
        privateField('phone', '電話', 429, 673, 120, 15, 'private.phone', 'tel'),
        privateField('land_section', '受災土地座落區段', 38, 618, 192, 15, 'private.land_section', 'off'),
        privateField('land_number', '地號', 239, 618, 146, 15, 'private.parcel_numbers', 'off'),
        privateField('land_share', '持分', 393, 618, 26, 15, 'private.land_share', 'off', false),
        field('land_area_ha', '經營面積（公頃）', 'text', 428, 618, 120, 15, 'matching.land_area_ha', true),
        {
          field_key: 'crop', label: '受災作物（給承辦看的備註）', type: 'text',
          required: false, editable: true, prefill_source: 'matching.crops',
          storage_scope: 'matching', helper_only: true, overlay: false,
          note: '作物種類、損失程度和金額是第二段「實地調查損失情形」的欄位，由調查人員到現場填，這裡只是先幫你記著要講什麼。'
        },
        helperQualification('這是旁邊的整理欄，不是官方受災證明書欄位，不會畫到政府表單。土地只疊第一列，其他列請到現場手寫。')
      ]
    }
  ];

  const GENERIC_PROGRAM_IDS = new Set([
    'afa-crop-insurance-sample',
    'afa-green-payment-enrollment',
    'moa-occupational-injury',
    'moa-retirement-savings'
  ]);

  // The browser keeps the local copy for privacy metadata and offline use,
  // but the checked-in manifest is the source of truth for PDF coordinates.
  // Merge the public mapping at runtime so a calibration change cannot leave
  // this fallback copy silently rendering stale positions.
  function mergeTemplateMapping(fallback, remote) {
    if (!fallback || !remote || !Array.isArray(remote.fields)) return fallback;
    const remoteByKey = new Map(remote.fields.map(field => [field.field_key, field]));
    const mergedFields = (fallback.fields || []).map(field => Object.assign(
      {}, field, remoteByKey.get(field.field_key) || {}
    ));
    const knownKeys = new Set(mergedFields.map(field => field.field_key));
    remote.fields.forEach(function (field) {
      if (!knownKeys.has(field.field_key)) mergedFields.push(Object.assign({}, field));
    });
    return Object.assign({}, fallback, remote, {fields: mergedFields});
  }

  // 從補助資料回頭找這筆申請對應的官方表單 id。優先比對同一個 variant／round，
  // 對不到才退回補助層——避免多方案的補助（例如農機有兩張表）抓錯那一張。
  async function lookupFormTemplateId(application) {
    if (!application || !application.program_id || typeof root.fetch !== 'function') return '';
    let program;
    try {
      const response = await root.fetch(
        '/programs/' + encodeURIComponent(application.program_id),
        {headers: {Accept: 'application/json'}});
      if (!response.ok) return '';
      program = await response.json();
    } catch (error) {
      return '';
    }
    for (const variant of program.variants || []) {
      if (application.variant_id && variant.id !== application.variant_id) continue;
      for (const round of variant.rounds || []) {
        if (application.round_id && round.id !== application.round_id) continue;
        if (round.form_template_id) return String(round.form_template_id);
      }
      if (variant.form_template_id) return String(variant.form_template_id);
    }
    return program.form_template_id ? String(program.form_template_id) : '';
  }

  async function resolveTemplate(params) {
    const fallback = selectTemplate(params);
    if (!fallback || typeof root.fetch !== 'function') return fallback;
    try {
      const response = await root.fetch(
        '/official-forms/templates/' + encodeURIComponent(fallback.id),
        {headers: {Accept: 'application/json'}}
      );
      if (!response.ok) return fallback;
      return mergeTemplateMapping(fallback, await response.json());
    } catch (error) {
      // A static/offline demo still works with the checked-in fallback.
      return fallback;
    }
  }

  // 沒註冊 → sessionStorage（關掉分頁就沒了）；註冊了 → localStorage。見 storage-mode.js
  function getStorage() {
    try {
      return root.AidStorage ? root.AidStorage.area() : root.sessionStorage;
    } catch (e) { return null; }
  }

  function readJson(key) {
    const store = getStorage();
    if (!store) return null;
    try {
      const raw = store.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function readFirst(keys) {
    for (const key of keys) {
      const value = readJson(key);
      if (value && typeof value === 'object') return value;
    }
    return {};
  }

  function writeJson(key, value) {
    const store = getStorage();
    if (!store) return false;
    try {
      store.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      return false;
    }
  }

  function isObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value);
  }

  function firstObject(value, keys) {
    if (!isObject(value)) return {};
    for (const key of keys) {
      if (isObject(value[key])) return value[key];
    }
    return value;
  }

  function loadProfiles() {
    const matchingRaw = readFirst(STORAGE_ALIASES.matching);
    const privateRaw = readFirst(STORAGE_ALIASES.privateForm);
    const generic = readJson('aidstation_profile') || {};

    const matching = firstObject(
      matchingRaw,
      ['matchingProfile', 'MatchingProfile', 'matching', 'profile', 'facts']
    );
    const privateForm = firstObject(
      privateRaw,
      ['privateFormProfile', 'PrivateFormProfile', 'private_form_profile', 'private', 'contact', 'profile']
    );

    // An envelope is convenient for a local-only profile page.  Sensitive
    // values still stay in this local object and never enter matching.
    if (isObject(generic.matchingProfile)) Object.assign(matching, generic.matchingProfile);
    if (isObject(generic.matching)) Object.assign(matching, generic.matching);
    if (isObject(generic.facts)) Object.assign(matching, generic.facts);
    if (isObject(generic.privateFormProfile)) Object.assign(privateForm, generic.privateFormProfile);
    if (isObject(generic.private)) Object.assign(privateForm, generic.private);
    if (isObject(generic.contact)) Object.assign(privateForm, generic.contact);

    return { matching: matching, privateForm: privateForm };
  }

  function pathValue(object, path) {
    if (!object || !path) return undefined;
    return path.split('.').reduce((current, key) => {
      if (current == null) return undefined;
      return current[key];
    }, object);
  }

  function aliasesValue(object, aliases) {
    for (const key of aliases || []) {
      const value = pathValue(object, key);
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return '';
  }

  function displayValue(value) {
    if (Array.isArray(value)) return value.join('、');
    if (value === true) return '有';
    if (value === false) return '沒有';
    if (value == null) return '';
    return String(value);
  }

  // 公文一律用民國年。申請日期預設今天——填表的人就是今天在填，
  // 但仍然可以改（例如補件時要寫原本的申請日）。
  function todayRocPart(part) {
    const now = new Date();
    if (part === 'year') return String(now.getFullYear() - 1911);
    if (part === 'month') return String(now.getMonth() + 1);
    if (part === 'day') return String(now.getDate());
    return '';
  }

  function fieldValue(field, profiles) {
    const source = field.prefill_source || '';
    const dot = source.indexOf('.');
    const scope = dot >= 0 ? source.slice(0, dot) : field.storage_scope;
    const key = dot >= 0 ? source.slice(dot + 1) : field.field_key;
    if (scope === 'today') return todayRocPart(key);
    if (scope === 'private' || field.storage_scope === 'private') {
      const aliases = PRIVATE_ALIASES[key] || PRIVATE_ALIASES[field.field_key] || [key, field.field_key];
      return displayValue(aliasesValue(profiles.privateForm, aliases));
    }
    if (scope === 'matching' || field.storage_scope === 'matching') {
      const aliases = MATCHING_ALIASES[key] || MATCHING_ALIASES[field.field_key] || [key, field.field_key];
      return displayValue(aliasesValue(profiles.matching, aliases));
    }
    return '';
  }

  function composeFormValues(template, profiles, draft) {
    const values = {};
    (template && template.fields || []).forEach(function (field) {
      if (draft && Object.prototype.hasOwnProperty.call(draft, field.field_key)) {
        values[field.field_key] = displayValue(draft[field.field_key]);
      } else {
        values[field.field_key] = fieldValue(field, profiles || {matching: {}, privateForm: {}});
      }
    });
    return values;
  }

  function safeId(value) {
    return String(value || '').replace(/[^a-zA-Z0-9_-]/g, '-');
  }

  function escapeText(value) {
    return displayValue(value);
  }

  function selectTemplate(params) {
    const askedId = params.get('template_id') || '';
    const exact = OFFICIAL_TEMPLATES.find(t => t.id === askedId);
    if (exact) return exact;

    // An explicit but unknown template id must never be guessed from a broad
    // programme name.  Guessing could show the wrong official attachment.
    if (!askedId && !params.get('program_id') && !params.get('program_name')) {
      return OFFICIAL_TEMPLATES.find(t => t.id === DEFAULT_TEMPLATE_ID);
    }
    return null;
  }

  function draftStorageKey(template, params) {
    const templateId = template ? template.id : 'no-official-template';
    const applicationId = params.get('application_id') || '';
    if (applicationId) return 'application::' + applicationId + '::' + templateId;
    const programId = params.get('program_id') || params.get('program_name') || 'direct';
    return templateId + '::' + programId;
  }

  function loadDraft(template, params) {
    const drafts = readJson(STORAGE_KEYS.drafts);
    if (!isObject(drafts)) return {};
    let value = drafts[draftStorageKey(template, params)];
    // Keep early demo drafts readable after an application record gets an
    // application-scoped key.  New saves never write to the broad key.
    if (!isObject(value) && params.get('application_id')) {
      const legacyProgram = params.get('program_id') || params.get('program_name') || 'direct';
      value = drafts[(template ? template.id : 'no-official-template') + '::' + legacyProgram];
    }
    return isObject(value) ? value : {};
  }

  function loadTaskProgress(template, params) {
    const progress = readJson(STORAGE_KEYS.tasks);
    if (!isObject(progress)) return {};
    const value = progress[draftStorageKey(template, params)];
    return isObject(value) ? value : {};
  }

  function saveTaskProgress(template, params, value) {
    const progress = readJson(STORAGE_KEYS.tasks);
    const next = isObject(progress) ? progress : {};
    next[draftStorageKey(template, params)] = value;
    return writeJson(STORAGE_KEYS.tasks, next);
  }

  function textElement(tag, className, text) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function storageLabel(scope) {
    if (scope === 'private') return {text: '你自己填的', className: 'local'};
    if (scope === 'matching') return {text: 'matching', className: 'matching'};
    return {text: '本次草稿', className: 'draft'};
  }

  function renderField(field, value, onChange) {
    const scope = field.storage_scope || 'display_only';
    const wrapper = textElement('div', 'field-card' + (field.type === 'textarea' || field.helper_only ? ' full-width' : ''));
    if (scope === 'private') wrapper.classList.add('local-field');
    if (scope === 'matching') wrapper.classList.add('matching-field');
    const row = textElement('div', 'field-label-row');
    const label = textElement('label', '', field.label);
    const inputId = 'field-' + safeId(field.field_key);
    label.htmlFor = inputId;
    if (field.required) {
      const required = textElement('span', 'required', ' 必填');
      required.setAttribute('aria-label', '必填');
      label.appendChild(required);
    }
    const badgeInfo = storageLabel(scope);
    row.appendChild(label);
    row.appendChild(textElement('span', 'storage-badge ' + badgeInfo.className, badgeInfo.text));
    wrapper.appendChild(row);

    const input = field.type === 'textarea' ? doc.createElement('textarea') : doc.createElement('input');
    input.id = inputId;
    input.name = field.field_key;
    input.className = 'field-value';
    input.value = escapeText(value);
    input.dataset.fieldKey = field.field_key;
    input.dataset.storageScope = scope;
    input.dataset.prefillSource = field.prefill_source || '';
    if (scope === 'private') input.dataset.privateField = 'true';
    if (scope === 'matching') input.dataset.matchingField = 'true';
    if (field.type !== 'textarea') input.type = field.type === 'number' ? 'number' : (field.type || 'text');
    if (field.autocomplete) input.autocomplete = field.autocomplete;
    if (field.inputmode) input.inputMode = field.inputmode;
    if (field.min !== undefined) input.min = field.min;
    if (field.max !== undefined) input.max = field.max;
    if (field.step !== undefined) input.step = field.step;
    if (field.required) input.required = true;
    if (field.editable === false) input.readOnly = true;
    input.addEventListener('input', function () {
      onChange(field.field_key, input.value);
    });
    wrapper.appendChild(input);

    const note = textElement('p', 'field-note', field.note || '');
    if (scope === 'private') note.classList.add('local-note');
    if (scope === 'matching' && value) note.classList.add('prefill-note');
    if (scope === 'matching' && value && !field.note) note.textContent = '已由當次 MatchingProfile 預填，可修改。';
    wrapper.appendChild(note);
    return wrapper;
  }

  function renderFieldGroup(container, title, description, fields, values, onChange) {
    // 少一個容器不該讓整份表單消失：舊版 form.html 搭配新版本檔時，
    // 這裡若直接 appendChild 就會丟例外並中斷 init()，連個人資料都不見。
    if (!container) return;
    const group = doc.createElement('fieldset');
    group.className = 'field-group';
    const legend = doc.createElement('legend');
    legend.appendChild(doc.createTextNode(title + ' '));
    if (description) legend.appendChild(textElement('small', '', description));
    group.appendChild(legend);
    const grid = textElement('div', 'field-grid');
    fields.forEach(function (field) {
      grid.appendChild(renderField(field, values[field.field_key] || '', onChange));
    });
    group.appendChild(grid);
    container.appendChild(group);
  }

  function canonicalPrivateKey(fieldKey) {
    return {
      applicant_name: 'full_name',
      phone: 'phone',
      national_id: 'national_id',
      birth_year: 'birth_year',
      address: 'full_address',
      land_number: 'parcel_numbers'
    }[fieldKey] || fieldKey;
  }

  function matchingSaveValue(fieldKey, value) {
    if (fieldKey === 'crop') {
      return String(value || '').split(/[、,，]/).map(x => x.trim()).filter(Boolean);
    }
    return value;
  }

  function collectValues(form, values, extraRoot) {
    const next = Object.assign({}, values);
    [form, extraRoot].filter(Boolean).forEach(function (container) {
      container.querySelectorAll('[data-field-key]').forEach(function (control) {
        next[control.dataset.fieldKey] = control.value;
      });
    });
    return next;
  }

  function saveProfiles(template, values, profiles, params) {
    const privateForm = Object.assign({}, profiles.privateForm || {});
    const matching = Object.assign({}, profiles.matching || {});
    (template && template.fields || []).forEach(function (field) {
      const value = values[field.field_key] == null ? '' : values[field.field_key];
      if (field.storage_scope === 'private') {
        privateForm[canonicalPrivateKey(field.field_key)] = value;
      } else if (field.storage_scope === 'matching') {
        matching[field.field_key] = matchingSaveValue(field.field_key, value);
      }
    });

    const drafts = readJson(STORAGE_KEYS.drafts);
    const nextDrafts = isObject(drafts) ? drafts : {};
    nextDrafts[draftStorageKey(template, params)] = values;
    let privateOk = writeJson(STORAGE_KEYS.privateForm, privateForm);
    // ProfileStore is the canonical versioned private profile used by the
    // profile page.  Keep the legacy key as a compatibility read path while
    // ensuring new edits are visible to both existing entry points.
    if (root.ProfileStore && typeof root.ProfileStore.save === 'function') {
      try {
        const canonical = root.ProfileStore.save(privateForm);
        Object.assign(privateForm, canonical || {});
        // The versioned key is a valid persistence path even when an older
        // browser key could not be written (for example after a migration).
        privateOk = true;
      } catch (e) {
        privateOk = false;
      }
    }
    const matchingOk = writeJson(STORAGE_KEYS.matching, matching);
    const draftOk = writeJson(STORAGE_KEYS.drafts, nextDrafts);
    return {
      privateForm: privateForm,
      matching: matching,
      ok: privateOk && matchingOk && draftOk
    };
  }

  function taskType(task) {
    const type = task && task.status_type;
    return ['completion', 'submission', 'form_submission'].includes(type) ? type : 'completion';
  }

  function localTaskState(progress, task) {
    const value = progress && progress[task.id];
    if (value && typeof value === 'object') {
      const type = taskType(task);
      return {
        completed: Boolean(value.completed),
        submitted: Boolean(value.submitted),
        filled: Boolean(value.filled),
        complete: type === 'form_submission' ? Boolean(value.filled && value.submitted)
          : type === 'submission' ? Boolean(value.submitted) : Boolean(value.completed),
      };
    }
    const done = Boolean(value);
    return {completed: done, submitted: done, filled: done, complete: done};
  }

  function taskStateLabel(task, state) {
    const type = taskType(task);
    if (type === 'form_submission') {
      return [state.filled ? '已填寫' : '待填寫', state.submitted ? '已送出' : '待送出'];
    }
    if (type === 'submission') return [state.submitted ? '已送出' : '待送出'];
    return [state.completed ? '已完成' : '待完成'];
  }

  function renderTasks(container, template, params, onChange, application, onOpenForm) {
    container.innerHTML = '';
    const appMode = Boolean(application && root.ApplicationStore);
    const tasks = appMode
      ? (application.items || [])
      : (template && template.tasks && template.tasks.length ? template.tasks : FALLBACK_TASKS);
    const legacyProgress = appMode ? null : loadTaskProgress(template, params);
    const count = doc.getElementById('task-count');
    const status = doc.getElementById('task-status');
    const nextNode = doc.getElementById('task-next');
    const completeButton = doc.getElementById('complete-application');
    const openFormButton = doc.getElementById('open-form');

    function currentRecord() {
      return appMode ? (root.ApplicationStore.get(application.id) || application) : null;
    }

    function refresh() {
      const record = currentRecord();
      const info = appMode ? root.ApplicationStore.progress(record) : {
        completed: tasks.filter(task => localTaskState(legacyProgress, task).complete).length,
        total: tasks.length,
      };
      info.percent = info.total ? Math.round(info.completed * 100 / info.total) : 0;
      if (count) count.textContent = info.completed + ' / ' + info.total + ' 項完成';
      const next = appMode ? root.ApplicationStore.nextTask(record) :
        tasks.find(task => !localTaskState(legacyProgress, task).complete);
      if (nextNode) nextNode.textContent = next ? '接下來：' + next.title : (appMode ? '所有申請項目都完成了，請確認完成申請。' : '目前清單已完成。');
      if (completeButton) completeButton.hidden = !appMode || !root.ApplicationStore.canComplete(record);
      if (openFormButton && appMode) openFormButton.textContent = template ? '編輯申請表' : '查看申請方式';
      container.querySelectorAll('.task-item').forEach(item => {
        const task = tasks.find(candidate => candidate.id === item.dataset.taskId);
        const state = appMode ? root.ApplicationStore.taskState(record, task) : localTaskState(legacyProgress, task);
        item.classList.toggle('done', Boolean(state.complete));
        item.querySelectorAll('input[data-task-key]').forEach(input => {
          const key = input.dataset.taskKey;
          input.checked = Boolean(state[key]);
        });
        item.querySelectorAll('[data-state-key]').forEach(node => {
          const key = node.dataset.stateKey;
          node.classList.toggle('active', Boolean(state[key]));
          node.textContent = key === 'filled' ? (state.filled ? '已填寫' : '待填寫') :
            key === 'submitted' ? (state.submitted ? '已送出' : '待送出') : (state.complete ? '已完成' : '待完成');
        });
      });
      if (status) status.textContent = info.completed ? '清單進度已留在這台裝置。' : '';
    }

    function addCheckbox(parent, task, state, key, labelText, change) {
      const label = textElement('label', 'task-control');
      const input = doc.createElement('input');
      input.type = 'checkbox';
      input.checked = Boolean(state[key]);
      input.dataset.taskKey = key;
      input.setAttribute('aria-label', task.title + '：' + labelText);
      input.addEventListener('change', () => change(input.checked));
      label.appendChild(input);
      label.appendChild(textElement('span', '', labelText));
      parent.appendChild(label);
    }

    tasks.forEach(function (task) {
      const item = textElement('article', 'task-item');
      item.dataset.taskId = task.id;
      const record = currentRecord();
      const state = appMode ? root.ApplicationStore.taskState(record, task) : localTaskState(legacyProgress, task);
      const copy = textElement('div', 'task-copy');
      copy.appendChild(textElement('span', 'task-title', task.title));
      copy.appendChild(textElement('span', 'task-description', task.description || ''));
      if (task.deadline) copy.appendChild(textElement('span', 'task-deadline', '期限：' + task.deadline));
      const states = textElement('div', 'task-states');
      taskStateLabel(task, state).forEach(label => {
        const key = label.indexOf('填') >= 0 ? 'filled' : label.indexOf('送') >= 0 ? 'submitted' : 'complete';
        states.appendChild(textElement('span', 'task-state' + (state[key] ? ' active' : ''), label));
      });
      copy.appendChild(states);
      item.appendChild(copy);
      const controls = textElement('div', 'task-controls');
      const type = taskType(task);
      if (appMode) {
        const update = patch => {
          const saved = root.ApplicationStore.updateTask(application.id, task.id, patch);
          if (saved) application = saved;
          refresh();
          if (onChange) onChange(Boolean(saved), saved);
        };
        if (type === 'completion') addCheckbox(controls, task, state, 'completed', '已完成', checked => update({completed: checked}));
        if (type === 'submission') addCheckbox(controls, task, state, 'submitted', '已送出', checked => update({submitted: checked}));
        if (type === 'form_submission') {
          addCheckbox(controls, task, state, 'filled', '已填寫', checked => update({filled: checked}));
          addCheckbox(controls, task, state, 'submitted', '已送出', checked => update({submitted: checked}));
          if (template) {
            const button = textElement('button', 'button small task-open-form', '編輯表單');
            button.type = 'button';
            button.addEventListener('click', () => { if (onOpenForm) onOpenForm(); });
            controls.appendChild(button);
          }
        }
        if (task.action_url) {
          const link = textElement('a', 'button small', task.action_label || '查看辦理方式');
          link.href = task.action_url;
          link.target = '_blank';
          link.rel = 'noopener';
          controls.appendChild(link);
        }
      } else {
        const checkbox = doc.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = Boolean(state.complete);
        checkbox.value = task.id;
        checkbox.setAttribute('aria-label', task.title);
        checkbox.addEventListener('change', function () {
          legacyProgress[task.id] = checkbox.checked;
          const saved = saveTaskProgress(template, params, legacyProgress);
          refresh();
          if (onChange) onChange(saved, null);
        });
        controls.appendChild(checkbox);
      }
      item.appendChild(controls);
      container.appendChild(item);
    });
    refresh();
    return refresh;
  }

  function positionNode(node, field) {
    const top = ((PDF_HEIGHT - Number(field.pos_y) - Number(field.height || 16)) / PDF_HEIGHT) * 100;
    node.style.left = (Number(field.pos_x) / PDF_WIDTH * 100) + '%';
    node.style.top = Math.max(0, top) + '%';
    node.style.width = (Number(field.width || 100) / PDF_WIDTH * 100) + '%';
    node.style.height = (Number(field.height || 16) / PDF_HEIGHT) * 100 + '%';
  }

  // 疊在官方 PDF 上的一律是唯讀文字，不是輸入框。編輯發生在上方分組好的欄位卡，
  // 那裡才有標籤、必填標記、「這筆存在哪」的標示與說明——直接在 PDF 上點小格子
  // 打字看不出這些，欄位一多也難按。PDF 的角色是「你填的字長在官方版面上的樣子」。
  function renderOfficialOverlay(overlay, template, values) {
    overlay.innerHTML = '';
    if (!template) return;
    (template.fields || []).filter(function (field) {
      return field.overlay !== false && field.pos_x != null && field.pos_y != null;
    }).forEach(function (field) {
      const span = textElement('span', 'overlay-text');
      span.dataset.overlayKey = field.field_key;
      positionNode(span, field);
      span.textContent = escapeText(values[field.field_key] || '');
      span.classList.toggle('empty', !span.textContent);
      overlay.appendChild(span);
    });
  }

  function updateOfficialOverlay(overlay, values) {
    if (!overlay) return;
    overlay.querySelectorAll('.overlay-text[data-overlay-key]').forEach(function (span) {
      const value = escapeText(values[span.dataset.overlayKey] || '');
      span.textContent = value;
      span.classList.toggle('empty', !value);
    });
  }

  function renderPreview(container, template, values) {
    container.innerHTML = '';
    const table = doc.createElement('table');
    table.className = 'preview-table';
    (template && template.fields || []).forEach(function (field) {
      const row = doc.createElement('tr');
      const head = doc.createElement('th');
      head.textContent = field.label;
      if (field.storage_scope === 'private') head.className = 'preview-private';
      if (field.storage_scope === 'matching') head.className = 'preview-matching';
      const cell = doc.createElement('td');
      const value = escapeText(values[field.field_key] || '');
      cell.textContent = value || '（未填）';
      if (!value) cell.className = 'preview-empty';
      row.appendChild(head);
      row.appendChild(cell);
      table.appendChild(row);
    });
    container.appendChild(table);
    const note = textElement('p', 'preview-notes', '本預覽只存在這台裝置；身分證、電話、姓名、出生年份與地址不會送往後端。這不是正式收件證明。');
    container.appendChild(note);
  }

  function setText(id, value) {
    const node = doc.getElementById(id);
    if (node) node.textContent = value || '—';
  }

  async function init() {
    const app = doc.querySelector('[data-form-app]');
    if (!app) return;
    const params = new URLSearchParams(root.location.search);
    const applicationId = params.get('application_id') || '';
    let application = applicationId && root.ApplicationStore
      ? root.ApplicationStore.get(applicationId) : null;
    if (applicationId && !application) {
      app.innerHTML = '<p class="empty-state">找不到這筆申請進度，請回「正在申請」重新選擇。</p>';
      return;
    }
    // 申請紀錄存在 localStorage，是按下「開始申請」那一刻的快照。補助之後才補上
    // 官方表單的話，舊紀錄裡的 form_template_id 會一直是空的，使用者永遠看不到
    // 那張表。所以空的時候回頭跟伺服器對一次，對到就補進紀錄。
    if (application && !application.form_template_id && !params.get('template_id')) {
      const found = await lookupFormTemplateId(application);
      if (found) {
        application = root.ApplicationStore.update
          ? (root.ApplicationStore.update(application.id, {form_template_id: found}) || application)
          : application;
        if (!application.form_template_id) application.form_template_id = found;
      }
    }
    if (application && application.form_template_id && !params.get('template_id')) {
      params.set('template_id', application.form_template_id);
    }
    if (application && application.program_id && !params.get('program_id')) {
      params.set('program_id', application.program_id);
    }
    const template = await resolveTemplate(params);
    const profiles = loadProfiles();
    const draft = loadDraft(template, params);
    const values = composeFormValues(template, profiles, draft);
    const programName = (application && application.program_name) || params.get('program_name') || (template && template.name) || '推薦申請項目';
    const variantName = application ? [application.variant_name, application.round_name].filter(Boolean).join('・') : '';

    setText('program-name', programName);
    setText('application-variant', variantName || '—');
    setText('template-name', template ? template.name : '目前沒有官方紙本表單');
    setText('official-page', template ? '第 ' + template.official_source_page + ' 頁・' + template.attachment : '—');
    setText('official-page-inline', template ? String(template.official_source_page) : '—');
    setText('official-attachment', template ? template.attachment + '｜' + template.name : '官方申請表');

    const formSection = doc.getElementById('form-section');
    const officialSection = doc.getElementById('official-section');
    const missing = doc.getElementById('official-missing');
    const sheetWrap = doc.getElementById('official-sheet-wrap');
    const overlay = doc.getElementById('official-overlay');
    const pdf = doc.getElementById('official-pdf');
    const openLink = doc.getElementById('official-open-link');
    const form = doc.getElementById('application-form');
    // 舊版 form.html 沒有這個容器就自己補一個，插在表單最前面（對應官方表單
    // 第一列的災害名稱與申請日期），少一個 div 不該讓整份表單消失。
    let draftFields = doc.getElementById('draft-fields');
    if (!draftFields && form) {
      draftFields = doc.createElement('div');
      draftFields.id = 'draft-fields';
      form.insertBefore(draftFields, form.firstChild);
    }
    const privateFields = doc.getElementById('private-fields');
    const matchingFields = doc.getElementById('matching-fields');
    const helperFields = doc.getElementById('helper-fields');
    const previewSection = doc.getElementById('preview-section');
    const previewContent = doc.getElementById('preview-content');
    const saveStatus = doc.getElementById('save-status');
    const openFormButton = doc.getElementById('open-form');
    let refreshTasks = null;

    function onFieldChange(key, value) {
      values[key] = value;
      updateOfficialOverlay(overlay, values);
    }

    function scrollToForm() {
      if (formSection) formSection.hidden = false;
      if (template && officialSection) officialSection.scrollIntoView({behavior: 'smooth', block: 'start'});
      else if (officialSection) officialSection.scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    if (openFormButton) openFormButton.addEventListener('click', scrollToForm);
    refreshTasks = renderTasks(doc.getElementById('task-list'), template, params, function (saved) {
      const status = doc.getElementById('task-status');
      if (status && !saved) {
        status.textContent = '瀏覽器暫時無法保存進度，請確認未使用無痕限制儲存。';
        status.classList.add('warn');
      }
    }, application, scrollToForm);

    if (!template) {
      if (openFormButton) {
        openFormButton.textContent = '查看申請方式';
        openFormButton.setAttribute('aria-controls', 'official-section');
      }
      if (formSection) formSection.hidden = false;
      const formHead = formSection && formSection.querySelector('.form-section-head');
      const legend = formSection && formSection.querySelector('.form-legend');
      if (formHead) formHead.hidden = true;
      if (legend) legend.hidden = true;
      if (form) form.hidden = true;
      if (missing) missing.hidden = false;
      if (sheetWrap) sheetWrap.hidden = true;
      if (openLink) openLink.hidden = true;
      const formActions = doc.getElementById('form-actions');
      if (formActions) formActions.hidden = true;
      const completeButton = doc.getElementById('complete-application');
      if (completeButton && application) completeButton.hidden = !root.ApplicationStore.canComplete(application);
      attachCompletion(application);
      return;
    }

    if (missing) missing.hidden = true;
    const pdfUrl = template.pdf_url || template.web_pdf;
    const previewImageUrl = template.preview_image;
    if (pdf) {
      pdf.src = previewImageUrl || pdfUrl;
      pdf.alt = template.name + '官方表單原始背景';
    }
    if (openLink) {
      openLink.href = pdfUrl;
      openLink.setAttribute('aria-label', '開新分頁看' + template.name + '原始 PDF');
    }
    renderOfficialOverlay(overlay, template, values);

    // 欄位依「這筆資料存在哪裡」分組，這是這頁要講清楚的第一件事：
    // 個資只留在本機、媒合欄位會同步、這次申請填的兩者都不寫回去。
    // 分組同時決定了 saveProfiles 把值寫去哪，所以畫面上的分法就是實際行為。
    const officialFields = (template.fields || []).filter(f => !f.helper_only);
    const privateList = officialFields.filter(f => f.storage_scope === 'private');
    const matchingList = officialFields.filter(f => f.storage_scope === 'matching');
    // 沒有 storage_scope 的（災害名稱、申請日期）每次申請都不一樣，
    // 只留在這張表的草稿裡，不寫回 MatchingProfile 也不寫進本機個資。
    const draftList = officialFields.filter(
      f => f.storage_scope !== 'private' && f.storage_scope !== 'matching');
    const helperList = (template.fields || []).filter(f => f.helper_only);

    if (privateFields) { privateFields.innerHTML = ''; privateFields.hidden = false; }
    if (matchingFields) { matchingFields.innerHTML = ''; matchingFields.hidden = false; }
    if (draftFields) { draftFields.innerHTML = ''; draftFields.hidden = false; }
    if (helperFields) helperFields.innerHTML = '';

    if (draftList.length) {
      renderFieldGroup(draftFields, '這次申請填的', '只留在這張表的草稿裡，不會存進你的常用資料。', draftList, values, onFieldChange);
    }
    renderFieldGroup(privateFields, '你的個人資料', '這些只存在你的手機或電腦裡，不會送出去。', privateList, values, onFieldChange);
    renderFieldGroup(matchingFields, '當次媒合欄位', '作物與申請條件可由 MatchingProfile 預填，仍可修改。', matchingList, values, onFieldChange);
    if (helperList.length) {
      renderFieldGroup(helperFields, '其他備註', '這些只是留給你自己看的，不會印到官方表單上。', helperList, values, onFieldChange);
    }

    function save(silent) {
      const nextValues = collectValues(form, values, overlay);
      Object.assign(values, nextValues);
      const saved = saveProfiles(template, values, profiles, params);
      profiles.privateForm = saved.privateForm;
      profiles.matching = saved.matching;
      updateOfficialOverlay(overlay, values);
      if (saveStatus) {
        saveStatus.classList.toggle('warn', !saved.ok);
        saveStatus.textContent = saved.ok
          ? (silent ? '已經存起來了。' : '已經存起來了，重新整理也還在。')
          : '瀏覽器暫時無法完整保存，請確認未使用無痕限制儲存。';
      }
      return saved.ok;
    }

    const saveButton = doc.getElementById('save-local');
    const previewButton = doc.getElementById('preview-form');
    const printButton = doc.getElementById('print-form');
    const closePreviewButton = doc.getElementById('close-preview');

    if (saveButton) saveButton.addEventListener('click', function () { save(false); });
    if (previewButton) previewButton.addEventListener('click', function () {
      save(true);
      renderPreview(previewContent, template, values);
      previewSection.hidden = false;
      previewSection.scrollIntoView({behavior: 'smooth', block: 'start'});
    });
    if (closePreviewButton) closePreviewButton.addEventListener('click', function () {
      previewSection.hidden = true;
    });
    function printOfficial() {
      save(true);
      officialSection.scrollIntoView({behavior: 'smooth', block: 'start'});
      root.setTimeout(function () { root.print(); }, 80);
    }
    if (printButton) printButton.addEventListener('click', printOfficial);
    attachCompletion(application);

    root.addEventListener('beforeprint', function () {
      updateOfficialOverlay(overlay, collectValues(form, values, overlay));
    });

    function attachCompletion(record) {
      const completeButton = doc.getElementById('complete-application');
      if (!completeButton || !record || !root.ApplicationStore) return;
      completeButton.onclick = function () {
        // Capture any direct-on-sheet edits before completing the application.
        if (template) save(true);
        const current = root.ApplicationStore.get(record.id) || record;
        if (!root.ApplicationStore.canComplete(current)) return;
        const done = root.ApplicationStore.complete(current.id);
        if (done) {
          completeButton.hidden = true;
          const status = doc.getElementById('task-status');
          if (status) status.textContent = '這筆申請已完成，已從「正在申請」移除。';
          root.setTimeout(() => { root.location.href = 'applications.html'; }, 500);
        }
      };
    }
  }

  root.FormPrefill = {
    STORAGE_KEYS: STORAGE_KEYS,
    OFFICIAL_TEMPLATES: OFFICIAL_TEMPLATES,
    GENERIC_PROGRAM_IDS: GENERIC_PROGRAM_IDS,
    loadProfiles: loadProfiles,
    selectTemplate: selectTemplate,
    mergeTemplateMapping: mergeTemplateMapping,
    resolveTemplate: resolveTemplate,
    composeFormValues: composeFormValues,
    displayValue: displayValue
  };

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
  else init();
})(window, document);
