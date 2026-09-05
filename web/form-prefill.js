/*
 * 農民補給站 browser-only Form Prefill
 *
 * The official PDF is always the visual source of truth.  This file only
 * reads localStorage, renders editable HTML controls, and places text spans
 * over the PDF at the coordinates in data/form_templates.json.  It does not
 * submit form values to a server.
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
    landline: ['landline', 'tel', 'phone', '電話']
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
    expected_delivery_date: ['expected_delivery_date', 'delivery_date', '預計交貨日期']
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
      description: '把作物、用途與已知條件整理在本機輔助欄位；實際資格仍由承辦認定。',
      depends_on: []
    },
    {
      id: 'complete-local-form',
      title: '檢查本機預填資料',
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
      pos_x: 140, pos_y: 593, width: 120, height: 16,
      required: true, editable: true, prefill_source: 'private.full_name',
      storage_scope: 'private', autocomplete: 'name'
    },
    {
      field_key: 'phone', label: '電話', type: 'text',
      pos_x: 375, pos_y: 593, width: 145, height: 16,
      required: true, editable: true, prefill_source: 'private.phone',
      storage_scope: 'private', autocomplete: 'tel'
    },
    {
      field_key: 'national_id', label: '身分證統一編號', type: 'text',
      pos_x: 165, pos_y: 572, width: 120, height: 16,
      required: true, editable: true, prefill_source: 'private.national_id',
      storage_scope: 'private', autocomplete: 'off'
    },
    {
      field_key: 'birth_year', label: '出生年份', type: 'text',
      pos_x: 389, pos_y: 572, width: 74, height: 16,
      required: true, editable: true, prefill_source: 'private.birth_year',
      storage_scope: 'private', inputmode: 'numeric'
    },
    {
      field_key: 'address', label: '地址', type: 'text',
      pos_x: 140, pos_y: 552, width: 245, height: 16,
      required: true, editable: true, prefill_source: 'private.full_address',
      storage_scope: 'private', autocomplete: 'street-address'
    },
    {
      field_key: 'crop', label: '種植作物種類', type: 'text',
      pos_x: 470, pos_y: 552, width: 70, height: 16,
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
      web_pdf: 'official-forms/labor_saving.pdf',
      official_layout: true,
      program_ids: ['farm-machine-115', 'afa115-appendix-09', 'afa-farm-machinery'],
      tasks: [
        { id: 'confirm-documents', title: '確認附表9與應備文件', description: '對照推薦卡的文件清單，整理好申請書、身分證件及承辦要求的附件。', depends_on: [] },
        { id: 'confirm-qualification', title: '補充申請資格說明', description: '把作物、農機用途與已知的驗證或資格資訊整理在旁邊；實際資格仍由承辦單位認定。', depends_on: [] },
        { id: 'complete-local-form', title: '檢查預填內容', description: '確認本機帶入的姓名、電話、身分證、出生年份、地址與媒合資料正確。', depends_on: ['confirm-documents'] },
        { id: 'print-and-visit', title: '預覽、列印並洽承辦', description: '列印官方附表9，帶著文件到推薦卡上的農會、公所或承辦單位確認。', depends_on: ['complete-local-form'] }
      ],
      fields: SHARED_PRIVATE_FIELDS.concat([
        field('machine_type', '農機機種', 'text', 232, 415, 145, 18, 'matching.machine_type', true),
        field('machine_model', '規格或牌型', 'text', 443, 415, 100, 18, 'matching.machine_model', true),
        field('score_items', '配分項目', 'text', 145, 381, 130, 16, 'matching.score_items', false),
        field('total_score', '總分', 'number', 320, 381, 42, 16, 'matching.total_score', false),
        field('expected_delivery_date', '預計交貨日期', 'text', 165, 272, 130, 16, 'matching.expected_delivery_date', false),
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
      web_pdf: 'official-forms/electric_replacement.pdf',
      official_layout: true,
      program_ids: ['farm-machine-115.electric-replacement', 'electric-replacement', 'afa115-appendix-16'],
      tasks: [
        { id: 'confirm-old-machine', title: '確認汰舊農機資料', description: '找出預計報廢燃油農機的證號或承辦要求的證明文件。', depends_on: [] },
        { id: 'confirm-qualification', title: '補充申請資格說明', description: '把作物、換購用途與已知的資格資訊整理在旁邊；實際資格仍由承辦單位認定。', depends_on: [] },
        { id: 'complete-local-form', title: '檢查預填內容', description: '確認本機帶入的姓名、電話、身分證、出生年份、地址與媒合資料正確。', depends_on: ['confirm-old-machine'] },
        { id: 'print-and-visit', title: '預覽、列印並洽承辦', description: '列印官方附表16，帶著文件到推薦卡上的農會、公所或承辦單位確認。', depends_on: ['complete-local-form'] }
      ],
      fields: SHARED_PRIVATE_FIELDS.concat([
        field('machine_type', '農機機種', 'text', 232, 415, 145, 18, 'matching.machine_type', true),
        field('machine_model', '規格或牌型', 'text', 443, 415, 100, 18, 'matching.machine_model', true),
        field('old_machine_cert_no', '預計報廢農機證號', 'text', 150, 439, 120, 16, 'matching.old_machine_cert_no', true),
        field('expected_delivery_date', '預計交貨日期', 'text', 165, 295, 130, 16, 'matching.expected_delivery_date', false),
        helperQualification('這是旁邊的整理欄，不是官方附表16欄位，不會畫到政府表單。')
      ])
    }
  ];

  const GENERIC_PROGRAM_IDS = new Set([
    'moa-disaster-cash-sample-2026',
    'afa-crop-insurance-sample',
    'afa-green-payment-enrollment',
    'moa-occupational-injury',
    'moa-retirement-savings'
  ]);

  function getStorage() {
    try { return root.localStorage; } catch (e) { return null; }
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

  function fieldValue(field, profiles) {
    const source = field.prefill_source || '';
    const dot = source.indexOf('.');
    const scope = dot >= 0 ? source.slice(0, dot) : field.storage_scope;
    const key = dot >= 0 ? source.slice(dot + 1) : field.field_key;
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
    const programId = params.get('program_id') || '';
    const programName = params.get('program_name') || '';
    const exact = OFFICIAL_TEMPLATES.find(t => t.id === askedId);
    if (exact) return exact;

    const haystack = (askedId + ' ' + programId + ' ' + programName).toLowerCase();
    if (/electric|replacement|換購|電動|汰舊/.test(haystack)) {
      return OFFICIAL_TEMPLATES.find(t => t.id === 'farm_machine_115.electric_replacement');
    }
    if (/labor|machine|machinery|農機|省工|新研發/.test(haystack)) {
      return OFFICIAL_TEMPLATES.find(t => t.id === 'farm_machine_115.labor_saving');
    }
    if (!askedId && !programId && !programName) {
      return OFFICIAL_TEMPLATES.find(t => t.id === DEFAULT_TEMPLATE_ID);
    }
    return null;
  }

  function draftStorageKey(template, params) {
    const templateId = template ? template.id : 'no-official-template';
    const programId = params.get('program_id') || params.get('program_name') || 'direct';
    return templateId + '::' + programId;
  }

  function loadDraft(template, params) {
    const drafts = readJson(STORAGE_KEYS.drafts);
    if (!isObject(drafts)) return {};
    const value = drafts[draftStorageKey(template, params)];
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
    if (scope === 'private') return {text: '本機 private', className: 'local'};
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
      address: 'full_address'
    }[fieldKey] || fieldKey;
  }

  function matchingSaveValue(fieldKey, value) {
    if (fieldKey === 'crop') {
      return String(value || '').split(/[、,，]/).map(x => x.trim()).filter(Boolean);
    }
    return value;
  }

  function collectValues(form, values) {
    const next = Object.assign({}, values);
    if (!form) return next;
    form.querySelectorAll('[data-field-key]').forEach(function (control) {
      next[control.dataset.fieldKey] = control.value;
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
    const privateOk = writeJson(STORAGE_KEYS.privateForm, privateForm);
    const matchingOk = writeJson(STORAGE_KEYS.matching, matching);
    const draftOk = writeJson(STORAGE_KEYS.drafts, nextDrafts);
    return {
      privateForm: privateForm,
      matching: matching,
      ok: privateOk && matchingOk && draftOk
    };
  }

  function renderTasks(container, template, params, onChange) {
    container.innerHTML = '';
    const tasks = template && template.tasks && template.tasks.length ? template.tasks : FALLBACK_TASKS;
    const progress = loadTaskProgress(template, params);
    const count = doc.getElementById('task-count');
    const status = doc.getElementById('task-status');

    function refresh() {
      const done = tasks.filter(task => progress[task.id]).length;
      if (count) count.textContent = done + ' / ' + tasks.length + ' 已完成';
      container.querySelectorAll('.task-item').forEach(item => {
        const input = item.querySelector('input');
        item.classList.toggle('done', Boolean(input && input.checked));
      });
      if (status) status.textContent = done ? '清單進度已留在這台裝置。' : '';
    }

    tasks.forEach(function (task) {
      const item = textElement('label', 'task-item');
      const checkbox = doc.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = task.id;
      checkbox.checked = Boolean(progress[task.id]);
      checkbox.setAttribute('aria-label', task.title);
      const copy = doc.createElement('span');
      copy.appendChild(textElement('span', 'task-title', task.title));
      copy.appendChild(textElement('span', 'task-description', task.description || ''));
      item.appendChild(checkbox);
      item.appendChild(copy);
      checkbox.addEventListener('change', function () {
        progress[task.id] = checkbox.checked;
        const saved = saveTaskProgress(template, params, progress);
        refresh();
        if (onChange) onChange(saved);
      });
      container.appendChild(item);
    });
    refresh();
  }

  function renderOfficialOverlay(overlay, template, values) {
    overlay.innerHTML = '';
    if (!template) return;
    (template.fields || []).filter(function (field) {
      return field.overlay !== false && field.pos_x != null && field.pos_y != null;
    }).forEach(function (field) {
      const span = textElement('span', 'overlay-text');
      const top = ((PDF_HEIGHT - Number(field.pos_y) - Number(field.height || 16)) / PDF_HEIGHT) * 100;
      span.dataset.overlayKey = field.field_key;
      span.style.left = (Number(field.pos_x) / PDF_WIDTH * 100) + '%';
      span.style.top = Math.max(0, top) + '%';
      span.style.width = (Number(field.width || 100) / PDF_WIDTH * 100) + '%';
      span.style.height = (Number(field.height || 16) / PDF_HEIGHT * 100) + '%';
      span.textContent = escapeText(values[field.field_key] || '');
      span.classList.toggle('empty', !span.textContent);
      overlay.appendChild(span);
    });
  }

  function updateOfficialOverlay(overlay, values) {
    if (!overlay) return;
    overlay.querySelectorAll('[data-overlay-key]').forEach(function (span) {
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

  function init() {
    const app = doc.querySelector('[data-form-app]');
    if (!app) return;
    const params = new URLSearchParams(root.location.search);
    const template = selectTemplate(params);
    const profiles = loadProfiles();
    const draft = loadDraft(template, params);
    const values = composeFormValues(template, profiles, draft);
    const programName = params.get('program_name') || (template && template.name) || '推薦申請項目';

    setText('program-name', programName);
    setText('template-name', template ? template.name : '目前沒有官方紙本表單');
    setText('official-page', template ? '第 ' + template.official_source_page + ' 頁・' + template.attachment : '—');
    setText('official-page-inline', template ? String(template.official_source_page) : '—');
    setText('official-attachment', template ? template.attachment + '｜' + template.name : '官方申請表');

    const taskList = doc.getElementById('task-list');
    renderTasks(taskList, template, params, function (saved) {
      const status = doc.getElementById('task-status');
      if (status && !saved) {
        status.textContent = '瀏覽器暫時無法保存進度，請確認未使用無痕限制儲存。';
        status.classList.add('warn');
      }
    });

    const formSection = doc.getElementById('form-section');
    const officialSection = doc.getElementById('official-section');
    const missing = doc.getElementById('official-missing');
    const sheetWrap = doc.getElementById('official-sheet-wrap');
    const overlay = doc.getElementById('official-overlay');
    const pdf = doc.getElementById('official-pdf');
    const openLink = doc.getElementById('official-open-link');
    const officialHelp = doc.getElementById('official-help');
    const overlayNote = doc.getElementById('official-overlay-note');
    const form = doc.getElementById('application-form');
    const privateFields = doc.getElementById('private-fields');
    const matchingFields = doc.getElementById('matching-fields');
    const helperFields = doc.getElementById('helper-fields');
    const previewSection = doc.getElementById('preview-section');
    const previewContent = doc.getElementById('preview-content');
    const saveStatus = doc.getElementById('save-status');
    const openFormButton = doc.getElementById('open-form');

    function onFieldChange(key, value) {
      values[key] = value;
      updateOfficialOverlay(overlay, values);
    }

    if (openFormButton) openFormButton.addEventListener('click', function () {
      if (!template) {
        officialSection.scrollIntoView({behavior: 'smooth', block: 'start'});
        return;
      }
      formSection.hidden = false;
      formSection.scrollIntoView({behavior: 'smooth', block: 'start'});
    });

    if (!template) {
      if (openFormButton) {
        openFormButton.textContent = '下一步：查看申請方式';
        openFormButton.setAttribute('aria-controls', 'official-section');
      }
      if (formSection) formSection.hidden = true;
      if (missing) missing.hidden = false;
      if (sheetWrap) sheetWrap.hidden = true;
      if (openLink) openLink.hidden = true;
      if (officialHelp) officialHelp.hidden = true;
      if (overlayNote) overlayNote.hidden = true;
      const officialActions = doc.getElementById('official-preview');
      if (officialActions) officialActions.parentElement.hidden = true;
      return;
    }

    if (missing) missing.hidden = true;
    const pdfUrl = template.pdf_url || template.web_pdf;
    if (pdf) {
      pdf.src = pdfUrl + '#toolbar=0&navpanes=0&view=FitH';
    }
    if (openLink) {
      openLink.href = pdfUrl;
      openLink.setAttribute('aria-label', '開新分頁看' + template.name + '原始 PDF');
    }
    renderOfficialOverlay(overlay, template, values);

    const officialFields = (template.fields || []).filter(f => !f.helper_only);
    const privateList = officialFields.filter(f => f.storage_scope === 'private');
    const matchingList = officialFields.filter(f => f.storage_scope === 'matching');
    const helperList = (template.fields || []).filter(f => f.helper_only);
    renderFieldGroup(privateFields, '本機私密欄位', '前五個欄位只從 localStorage 的 PrivateFormProfile 預填。', privateList, values, onFieldChange);
    renderFieldGroup(matchingFields, '當次媒合欄位', '作物與申請條件可由 MatchingProfile 預填，仍可修改。', matchingList, values, onFieldChange);
    if (helperList.length) {
      renderFieldGroup(helperFields, '申請準備輔助欄位', '沒有官方座標的備註只留在本機，不會畫到官方 PDF。', helperList, values, onFieldChange);
    }

    function save(silent) {
      const nextValues = collectValues(form, values);
      Object.assign(values, nextValues);
      const saved = saveProfiles(template, values, profiles, params);
      profiles.privateForm = saved.privateForm;
      profiles.matching = saved.matching;
      updateOfficialOverlay(overlay, values);
      if (saveStatus) {
        saveStatus.classList.toggle('warn', !saved.ok);
        saveStatus.textContent = saved.ok
          ? (silent ? '已儲存本機資料。' : '已儲存本機資料；重新整理後仍會保留。')
          : '瀏覽器暫時無法完整保存，請確認未使用無痕限制儲存。';
      }
      return saved.ok;
    }

    const saveButton = doc.getElementById('save-local');
    const previewButton = doc.getElementById('preview-form');
    const printButton = doc.getElementById('print-form');
    const officialPreviewButton = doc.getElementById('official-preview');
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
    if (officialPreviewButton) officialPreviewButton.addEventListener('click', printOfficial);

    root.addEventListener('beforeprint', function () {
      updateOfficialOverlay(overlay, collectValues(form, values));
    });
  }

  root.FormPrefill = {
    STORAGE_KEYS: STORAGE_KEYS,
    OFFICIAL_TEMPLATES: OFFICIAL_TEMPLATES,
    GENERIC_PROGRAM_IDS: GENERIC_PROGRAM_IDS,
    loadProfiles: loadProfiles,
    selectTemplate: selectTemplate,
    composeFormValues: composeFormValues,
    displayValue: displayValue
  };

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
  else init();
})(window, document);
