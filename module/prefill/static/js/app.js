/* global PDFLib */
const App = (() => {
  let fields = [];
  let currentTemplate = null;
  let currentVersion = null;
  let currentAid = null;
  let profileCache = null;

  function show(id) {
    document.querySelectorAll('main > section').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(id);
    if (target) target.classList.remove('hidden');
  }

  function isPresent(value) {
    return value !== undefined && value !== null && String(value).trim() !== '';
  }

  function asBoolean(value) {
    return value === true || value === 1 || value === '1' ||
      value === 'true' || value === 'yes' || value === '有';
  }

  function fieldControls(field) {
    return [...document.querySelectorAll('#prefill-form [data-field-key]')]
      .filter(el => el.dataset.fieldKey === field.field_key);
  }

  function fieldValue(field) {
    const controls = fieldControls(field);
    if (field.type === 'checkbox') return Boolean(controls[0]?.checked);
    if (field.type === 'radio') {
      return controls.find(control => control.checked)?.value || '';
    }
    return controls[0]?.value || '';
  }

  function fieldIsEmpty(field) {
    if (field.type === 'checkbox') return !fieldValue(field);
    return !isPresent(fieldValue(field));
  }

  function missingRequiredFields() {
    return fields
      .filter(field => field.required && fieldIsEmpty(field))
      .map(field => field.label);
  }

  function setValidation(msg, missing) {
    const el = document.getElementById('validation-msg');
    el.innerHTML = '';
    if (!missing.length) {
      el.textContent = '✓ 必填欄位皆已完成';
      el.className = 'validation-msg ok';
      return;
    }
    el.appendChild(document.createTextNode(msg));
    const list = document.createElement('ul');
    missing.forEach(label => {
      const item = document.createElement('li');
      item.textContent = label;
      list.appendChild(item);
    });
    el.appendChild(list);
    el.className = 'validation-msg error';
  }

  function coordinatesReady() {
    return Boolean(currentVersion?.pdf_available) &&
      fields.every(field => Number(field.coordinates_calibrated) !== 0);
  }

  function updateFormState() {
    const missing = missingRequiredFields();
    setValidation('還有需要填寫的欄位：', missing);
    const ready = !missing.length && coordinatesReady();
    document.getElementById('btn-preview').disabled = !ready;
    document.getElementById('btn-download').disabled = !ready;

    const status = document.getElementById('pdf-status');
    if (!currentVersion) {
      status.textContent = '';
      status.className = 'pdf-status';
    } else if (!currentVersion.pdf_available) {
      status.textContent = '這份模板目前只有官方原始 PDF；本機 PDF 尚未匯入，因此暫時不能產生疊字檔。';
      status.className = 'pdf-status warning';
    } else if (!coordinatesReady()) {
      status.textContent = 'PDF 已匯入，但欄位座標尚未校準；完成校準後才能預覽或下載。';
      status.className = 'pdf-status warning';
    } else {
      status.textContent = '填寫內容只會儲存在這台裝置的瀏覽器。';
      status.className = 'pdf-status ok';
    }
  }

  async function loadProfiles() {
    if (profileCache) return profileCache;
    const all = await IDB.getAll('profiles');
    const map = Object.fromEntries(all.map(profile => [profile.key, profile.value]));
    if (!Object.keys(map).length) {
      try {
        const response = await fetch('/api/profiles');
        if (response.ok) {
          const server = await response.json();
          for (const [key, value] of Object.entries(server)) {
            await IDB.put('profiles', { key, value });
            map[key] = value;
          }
        }
      } catch (error) {
        console.warn('load profiles failed', error);
      }
    }
    profileCache = map;
    return map;
  }

  async function findDraft(versionId) {
    const applications = await IDB.getAll('applications');
    return applications
      .filter(application => application.template_version_id === versionId)
      .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))[0];
  }

  function normaliseOptions(field) {
    if (!Array.isArray(field.options)) return [];
    return field.options.map(option => {
      if (option && typeof option === 'object') {
        const value = option.value ?? option.id ?? option.label;
        return { value: String(value ?? ''), label: String(option.label ?? value ?? '') };
      }
      return { value: String(option), label: String(option) };
    }).filter(option => option.value && option.label);
  }

  function appendFieldHint(row, field) {
    if (field.note) {
      const note = document.createElement('small');
      note.className = 'field-note';
      note.textContent = field.note;
      row.appendChild(note);
    }
    if (field.privacy === 'local_only') {
      const privacy = document.createElement('small');
      privacy.className = 'privacy-note';
      privacy.textContent = '🔒 僅存本機，不會送回伺服器';
      row.appendChild(privacy);
    }
  }

  function setInitialValue(field, controls, value, fromPrefill) {
    if (field.type === 'checkbox') {
      controls[0].checked = asBoolean(value);
    } else if (field.type === 'radio') {
      controls.forEach(control => {
        control.checked = String(value ?? '') === control.value;
      });
    } else if (value !== undefined && value !== null) {
      controls[0].value = String(value);
    }
    if (fromPrefill && isPresent(value)) {
      controls.forEach(control => { control.dataset.prefilled = 'true'; });
    }
  }

  async function renderForm(draftData = {}) {
    const form = document.getElementById('prefill-form');
    form.innerHTML = '';
    const profiles = await loadProfiles();

    fields.forEach(field => {
      const row = document.createElement('div');
      row.className = 'form-row';
      row.dataset.fieldKey = field.field_key;

      const profileKey = field.prefill_source?.startsWith('profile.')
        ? field.prefill_source.replace('profile.', '')
        : null;
      const hasDraftValue = Object.prototype.hasOwnProperty.call(draftData, field.field_key);
      const initialValue = hasDraftValue ? draftData[field.field_key] : profiles[profileKey];
      const fromPrefill = !hasDraftValue && Boolean(profileKey);
      let controls = [];

      if (field.type === 'checkbox') {
        const wrapper = document.createElement('div');
        wrapper.className = 'checkbox-control';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = field.field_key;
        input.name = field.field_key;
        input.dataset.fieldKey = field.field_key;
        input.disabled = !field.editable;
        input.className = field.required ? 'required' : '';
        const label = document.createElement('label');
        label.htmlFor = field.field_key;
        label.textContent = field.label + (field.required ? ' *' : '');
        wrapper.append(input, label);
        row.appendChild(wrapper);
        controls = [input];
      } else if (field.type === 'radio' && normaliseOptions(field).length) {
        const group = document.createElement('fieldset');
        group.className = 'radio-group';
        const legend = document.createElement('legend');
        legend.textContent = field.label + (field.required ? ' *' : '');
        group.appendChild(legend);
        normaliseOptions(field).forEach((option, index) => {
          const optionLabel = document.createElement('label');
          optionLabel.className = 'radio-option';
          const input = document.createElement('input');
          input.type = 'radio';
          input.id = `${field.field_key}-${index}`;
          input.name = field.field_key;
          input.value = option.value;
          input.dataset.fieldKey = field.field_key;
          input.disabled = !field.editable;
          input.className = field.required ? 'required' : '';
          optionLabel.append(input, document.createTextNode(option.label));
          group.appendChild(optionLabel);
          controls.push(input);
        });
        row.appendChild(group);
      } else {
        const label = document.createElement('label');
        label.textContent = field.label + (field.required ? ' *' : '');
        label.htmlFor = field.field_key;
        const input = document.createElement('input');
        input.type = ['number', 'date'].includes(field.type) ? field.type : 'text';
        input.id = field.field_key;
        input.name = field.field_key;
        input.dataset.fieldKey = field.field_key;
        input.dataset.logicalType = field.type || 'text';
        input.readOnly = !field.editable;
        input.className = field.required ? 'required' : '';
        row.append(label, input);
        controls = [input];
        if (field.type === 'radio') {
          const note = document.createElement('small');
          note.className = 'field-note';
          note.textContent = '此欄位尚未提供選項，請依官方表單填寫。';
          row.appendChild(note);
        }
      }

      setInitialValue(field, controls, initialValue, fromPrefill);
      controls.forEach(control => {
        control.addEventListener('input', updateFormState);
        control.addEventListener('change', updateFormState);
      });
      appendFieldHint(row, field);
      form.appendChild(row);
    });
    updateFormState();
  }

  function formData() {
    return Object.fromEntries(fields.map(field => [field.field_key, fieldValue(field)]));
  }

  async function validateForm() {
    const missing = missingRequiredFields();
    setValidation('還有需要填寫的欄位：', missing);
    return missing.length === 0;
  }

  async function saveDraft() {
    if (!currentVersion) return;
    const payload = {
      id: currentAid || ('app_' + Date.now()),
      template_id: currentTemplate.id,
      template_version_id: currentVersion.id,
      data: formData(),
      status: 'draft',
      updated_at: new Date().toISOString(),
    };
    await IDB.put('applications', payload);
    currentAid = payload.id;
    alert('草稿已儲存在本機瀏覽器');
  }

  async function buildFilledPdf() {
    if (!coordinatesReady()) throw new Error('PDF 尚未準備好');
    const { PDFDocument } = PDFLib;
    const response = await fetch(`/api/template-versions/${currentVersion.id}/pdf`);
    if (!response.ok) throw new Error('PDF 下載失敗');
    const pdfDoc = await PDFDocument.load(await response.arrayBuffer());
    const pages = pdfDoc.getPages();
    const font = await pdfDoc.embedFont(PDFLib.StandardFonts.Helvetica);
    for (const field of fields) {
      const pageIdx = Math.max(0, (field.page || 1) - 1);
      const page = pages[pageIdx];
      if (!page || Number(field.coordinates_calibrated) === 0) continue;
      const value = fieldValue(field);
      if (field.type === 'checkbox' && value) {
        page.drawText('X', { x: Number(field.pos_x), y: Number(field.pos_y), size: 12, font, color: PDFLib.rgb(0, 0, 0) });
      } else if (field.type !== 'checkbox' && isPresent(value)) {
        page.drawText(String(value), {
          x: Number(field.pos_x),
          y: Number(field.pos_y),
          size: 12,
          font,
          color: PDFLib.rgb(0, 0, 0),
        });
      }
    }
    return await pdfDoc.save();
  }

  async function previewPdf() {
    if (!await validateForm()) return;
    try {
      const bytes = await buildFilledPdf();
      const blob = new Blob([bytes], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      document.getElementById('pdf-iframe').src = url;
      document.getElementById('btn-download').disabled = false;
    } catch (error) {
      alert(`目前無法產生填妥 PDF：${error.message}`);
    }
  }

  async function downloadPdf() {
    if (!await validateForm()) return;
    try {
      const bytes = await buildFilledPdf();
      const blob = new Blob([bytes], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `申請表_${new Date().toISOString().slice(0, 10)}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      alert(`目前無法下載填妥 PDF：${error.message}`);
    }
  }

  function setPdfPreview() {
    const iframe = document.getElementById('pdf-iframe');
    if (!currentVersion) {
      iframe.src = '';
      return;
    }
    if (currentVersion.pdf_available) {
      iframe.src = currentVersion.pdf_url || `/api/template-versions/${currentVersion.id}/pdf`;
    } else if (currentVersion.source_pdf_url) {
      iframe.src = `${currentVersion.source_pdf_url}#page=${currentVersion.source_page || 1}`;
    } else {
      iframe.src = '';
    }
  }

  async function openTemplate(template, version) {
    const response = await fetch(`/api/template-versions/${version.id}/fields`);
    if (!response.ok) throw new Error('欄位載入失敗');
    fields = await response.json();
    currentTemplate = template;
    currentVersion = version;
    const draft = await findDraft(version.id);
    currentAid = draft?.id || null;
    document.getElementById('form-title').textContent = template.name;
    document.getElementById('pdf-title').textContent = `${template.name}｜原始表單預覽`;
    setPdfPreview();
    show('application-area');
    await renderForm(draft?.data || {});
  }

  async function loadTemplateVersions() {
    const response = await fetch('/api/templates');
    if (!response.ok) throw new Error('模板列表載入失敗');
    const templates = await response.json();
    const container = document.getElementById('template-list');
    container.innerHTML = '';
    if (!templates.length) {
      container.textContent = '尚無表單模板';
      return;
    }

    for (const template of templates) {
      const versionsResponse = await fetch(`/api/templates/${template.id}/versions`);
      if (!versionsResponse.ok) continue;
      const versions = await versionsResponse.json();
      const latest = versions[0];
      if (!latest) continue;

      const card = document.createElement('div');
      card.className = 'card';
      const title = document.createElement('h4');
      title.textContent = template.name;
      const version = document.createElement('p');
      version.textContent = `版本：${latest.version}`;
      card.append(title, version);
      if (latest.usage) {
        const usage = document.createElement('p');
        usage.className = 'card-note';
        usage.textContent = latest.usage;
        card.appendChild(usage);
      }
      if (latest.source_page) {
        const source = document.createElement('p');
        source.className = 'card-note';
        source.textContent = `官方 PDF 第 ${latest.source_page} 頁`;
        card.appendChild(source);
      }
      const button = document.createElement('button');
      button.className = 'btn primary';
      button.textContent = '開啟申請表';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try {
          await openTemplate(template, latest);
        } catch (error) {
          alert(`表單載入失敗：${error.message}`);
        } finally {
          button.disabled = false;
        }
      });
      card.appendChild(button);
      container.appendChild(card);
    }
  }

  function bind() {
    document.getElementById('btn-back').addEventListener('click', () => {
      currentTemplate = null;
      currentVersion = null;
      currentAid = null;
      fields = [];
      show('template-select');
      loadTemplateVersions().catch(error => alert(`模板載入失敗：${error.message}`));
    });
    document.getElementById('btn-save').addEventListener('click', saveDraft);
    document.getElementById('btn-preview').addEventListener('click', previewPdf);
    document.getElementById('btn-download').addEventListener('click', downloadPdf);
    document.querySelectorAll('.app-nav a').forEach(link => {
      link.addEventListener('click', event => {
        if (link.getAttribute('href') === '/profile') {
          event.preventDefault();
          alert('此功能會延伸到 /profile 頁面，目前先專注於申請表流程');
        }
      });
    });
    document.getElementById('modal-close').addEventListener('click', () => {
      document.getElementById('modal').classList.add('hidden');
    });
  }

  async function init() {
    bind();
    try {
      await loadTemplateVersions();
    } catch (error) {
      document.getElementById('template-list').textContent = `模板載入失敗：${error.message}`;
    }
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', App.init);
