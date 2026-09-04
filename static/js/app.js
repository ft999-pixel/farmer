/* global PDFLib */
const App = (() => {
  let templateVersions = [];
  let fields = [];
  let currentAid = null;

  function show(id) {
    document.querySelectorAll('main > section').forEach(el => el.classList.add('hidden'));
    const target = document.getElementById(id);
    if (target) target.classList.remove('hidden');
  }

  function setValidation(msg, missing) {
    const el = document.getElementById('validation-msg');
    if (!missing.length) {
      el.textContent = '✓ 必填欄位皆已完成';
      el.className = 'validation-msg ok';
      return;
    }
    el.innerHTML = `${msg}<ul>${missing.map(m => `<li>${m}</li>`).join('')}</ul>`;
    el.className = 'validation-msg error';
  }

  async function loadProfiles() {
    const all = await IDB.getAll('profiles');
    const map = Object.fromEntries(all.map(p => [p.key, p.value]));
    if (!Object.keys(map).length) {
      try {
        const server = await fetch('/api/profiles').then(r => r.json());
        for (const [k, v] of Object.entries(server)) {
          await IDB.put('profiles', { key: k, value: v });
          map[k] = v;
        }
      } catch (e) {
        console.warn('load profiles failed', e);
      }
    }
    return map;
  }

  async function loadApplications() {
    return await IDB.getAll('applications');
  }

  async function resolvePrefill(source) {
    if (!source) return '';
    if (source.startsWith('profile.')) {
      const profiles = await loadProfiles();
      const key = source.replace('profile.', '');
      return profiles[key] || '';
    }
    return '';
  }

  async function renderForm() {
    const form = document.getElementById('prefill-form');
    form.innerHTML = '';
    const profiles = await loadProfiles();
    let missing = [];
    fields.forEach(f => {
      const row = document.createElement('div');
      row.className = 'form-row';
      const label = document.createElement('label');
      label.textContent = f.label + (f.required ? ' *' : '');
      label.setAttribute('for', f.field_key);
      const input = document.createElement('input');
      input.type = f.type === 'number' ? 'number' : 'text';
      input.id = f.field_key;
      input.name = f.field_key;
      input.dataset.prefill = f.prefill_source || '';
      input.readOnly = !f.editable;
      input.className = f.required ? 'required' : '';
      if (f.prefill_source && profiles[f.prefill_source.replace('profile.', '')]) {
        input.value = profiles[f.prefill_source.replace('profile.', '')];
        input.dataset.prefilled = 'true';
      }
      if (f.required && !input.value) missing.push(f.label);
      input.addEventListener('input', () => {
        if (f.required) {
          const m = [...document.querySelectorAll('#prefill-form .required')].filter(el => !el.value).map(el => fields.find(ff => ff.field_key === el.name)?.label).filter(Boolean);
          setValidation('還有需要填寫的欄位：', m);
          document.getElementById('btn-preview').disabled = !!m.length;
          document.getElementById('btn-download').disabled = !!m.length;
        }
      });
      row.appendChild(label);
      row.appendChild(input);
      form.appendChild(row);
    });
    setValidation('還有需要填寫的欄位：', missing);
  }

  async function validateForm() {
    const missing = [];
    document.querySelectorAll('#prefill-form .required').forEach(el => {
      if (!el.value) missing.push(fields.find(f => f.field_key === el.name)?.label || el.name);
    });
    setValidation('還有需要填寫的欄位：', missing);
    return missing.length === 0;
  }

  async function saveDraft() {
    const data = {};
    document.querySelectorAll('#prefill-form input').forEach(el => {
      data[el.name] = el.value;
    });
    if (!currentAid) {
      const app = await IDB.get('applications', 'current');
      currentAid = app?.id || undefined;
    }
    const payload = {
      id: currentAid || ('app_' + Date.now()),
      template_version_id: templateVersions[0]?.id || '',
      data,
      status: 'draft',
      updated_at: new Date().toISOString()
    };
    await IDB.put('applications', payload);
    currentAid = payload.id;
    alert('草稿已儲存在本機瀏覽器');
  }

  async function buildFilledPdf() {
    const { PDFDocument } = PDFLib;
    const pdfBytes = await fetch(`/api/template-versions/${templateVersions[0]?.id}/pdf`).then(r => r.arrayBuffer());
    const pdfDoc = await PDFDocument.load(pdfBytes);
    const pages = pdfDoc.getPages();
    const font = await pdfDoc.embedFont(PDFLib.StandardFonts.Helvetica);
    for (const f of fields) {
      const pageIdx = Math.max(0, (f.page || 1) - 1);
      const page = pages[pageIdx];
      if (!page) continue;
      const inputEl = document.getElementById(f.field_key);
      const value = inputEl?.value || '';
      page.drawText(value || ' ', {
        x: f.pos_x,
        y: f.pos_y,
        size: 12,
        font,
        color: PDFLib.rgb(0, 0, 0),
      });
    }
    return await pdfDoc.save();
  }

  async function previewPdf() {
    const ok = await validateForm();
    if (!ok) return;
    const bytes = await buildFilledPdf();
    const blob = new Blob([bytes], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    document.getElementById('pdf-iframe').src = url;
    document.getElementById('btn-download').disabled = false;
  }

  async function downloadPdf() {
    const ok = await validateForm();
    if (!ok) return;
    const bytes = await buildFilledPdf();
    const blob = new Blob([bytes], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `申請表_${new Date().toISOString().slice(0,10)}.pdf`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function loadTemplateVersions() {
    const res = await fetch('/api/templates').then(r => r.json());
    const container = document.getElementById('template-list');
    container.innerHTML = '';
    if (!res.length) {
      container.innerHTML = '<p>尚無表單模板</p>';
      return;
    }
    for (const t of res) {
      const versions = await fetch(`/api/templates/${t.id}/versions`).then(r => r.json());
      const latest = versions[0];
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <h4>${t.name}</h4>
        <p>版本：${latest?.version || '-'}</p>
        <button class="btn primary" data-vid="${latest?.id}">開啟申請表</button>
      `;
      card.querySelector('button').addEventListener('click', async () => {
        fields = await fetch(`/api/template-versions/${latest.id}/fields`).then(r => r.json());
        templateVersions = [{ ...t, version_id: latest.id }];
        document.getElementById('form-title').textContent = t.name;
        await renderForm();
        document.getElementById('pdf-iframe').src = `/api/template-versions/${latest.id}/pdf`;
        show('application-area');
      });
      container.appendChild(card);
    }
  }

  function bind() {
    document.getElementById('btn-back').addEventListener('click', () => {
      show('template-select');
      loadTemplateVersions();
    });
    document.getElementById('btn-save').addEventListener('click', saveDraft);
    document.getElementById('btn-preview').addEventListener('click', previewPdf);
    document.getElementById('btn-download').addEventListener('click', downloadPdf);
    document.querySelectorAll('.app-nav a').forEach(a => {
      a.addEventListener('click', (e) => {
        if (a.getAttribute('href') === '/profile') {
          e.preventDefault();
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
    await loadTemplateVersions();
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', App.init);
