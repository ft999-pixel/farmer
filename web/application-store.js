/*
 * Browser-only application progress store.
 *
 * This module deliberately stores only public programme/round metadata and
 * task checkpoints.  Private form values remain in the existing prefill
 * storage and are never copied into an application record or a request.
 */
(function (root, factory) {
  const store = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = store;
  else root.ApplicationStore = store;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';

  const STORAGE_KEY = 'aidstation_applications_v1';
  const VERSION = 1;
  const STATUS_TYPES = Object.freeze(['completion', 'submission', 'form_submission']);

  function storage() {
    try { return root && root.localStorage ? root.localStorage : null; }
    catch (e) { return null; }
  }

  function isObject(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
  }

  function clone(value) {
    if (value == null) return value;
    try { return JSON.parse(JSON.stringify(value)); }
    catch (e) { return value; }
  }

  function readEnvelope() {
    const store = storage();
    if (!store) return {version: VERSION, applications: []};
    try {
      const parsed = JSON.parse(store.getItem(STORAGE_KEY) || '{}');
      if (Array.isArray(parsed)) return {version: VERSION, applications: parsed};
      if (isObject(parsed) && Array.isArray(parsed.applications)) {
        return {version: parsed.version || VERSION, applications: parsed.applications};
      }
    } catch (e) {}
    return {version: VERSION, applications: []};
  }

  function writeEnvelope(envelope) {
    const store = storage();
    if (!store) return false;
    try {
      store.setItem(STORAGE_KEY, JSON.stringify({
        version: VERSION,
        applications: envelope.applications,
      }));
      return true;
    } catch (e) { return false; }
  }

  function now() { return new Date().toISOString(); }

  function newId() {
    try {
      if (root.crypto && typeof root.crypto.randomUUID === 'function') {
        return 'application-' + root.crypto.randomUUID();
      }
    } catch (e) {}
    return 'application-' + Date.now().toString(36) + '-' +
      Math.random().toString(36).slice(2, 10);
  }

  function text(value) {
    return value == null ? '' : String(value);
  }

  function normaliseType(value) {
    return STATUS_TYPES.includes(value) ? value : 'completion';
  }

  function normaliseTask(task, index) {
    const source = isObject(task) ? task : {};
    const id = text(source.id || 'task-' + (index + 1));
    const title = text(source.title || source.name || '申請項目 ' + (index + 1));
    const description = text(source.description).trim() || `完成「${title}」後，再繼續下一步。`;
    const depends = Array.isArray(source.depends_on) ? source.depends_on.map(text) : [];
    return {
      id,
      title,
      description,
      deadline: source.deadline == null ? null : text(source.deadline),
      depends_on: depends,
      status_type: normaliseType(source.status_type),
      action_label: source.action_label == null ? '' : text(source.action_label),
      action_url: source.action_url == null ? '' : text(source.action_url),
    };
  }

  function taskList(context) {
    const source = context || {};
    const round = source.round || {};
    const variant = source.variant || {};
    const program = source.program || {};
    const candidates = [round.tasks, variant.tasks, program.tasks];
    let tasks = candidates.find(candidate =>
      (Array.isArray(candidate) && candidate.length) || isObject(candidate)
    );
    if (isObject(tasks)) tasks = [tasks];
    if ((!Array.isArray(tasks) || !tasks.length) && program.plain && Array.isArray(program.plain.steps)) {
      tasks = program.plain.steps.map((title, index) => ({
        id: 'plain-step-' + (index + 1),
        title: typeof title === 'string' ? title.replace(/\*\*/g, '') : '申請步驟 ' + (index + 1),
        description: '依補助說明完成這個步驟，細節請向承辦單位確認。',
        status_type: 'completion',
        depends_on: index ? ['plain-step-' + index] : [],
      }));
    }
    return (Array.isArray(tasks) ? tasks : []).map(normaliseTask);
  }

  function contextIds(context) {
    const source = context || {};
    const program = source.program || {};
    const variant = source.variant || {};
    const round = source.round || {};
    return {
      program_id: text(source.program_id || program.id),
      variant_id: text(source.variant_id || variant.id),
      round_id: text(source.round_id || round.id),
    };
  }

  function scopeKey(context) {
    const ids = contextIds(context);
    return [ids.program_id || 'program', ids.variant_id || 'variant', ids.round_id || 'round'].join('::');
  }

  function displayContext(context) {
    const source = context || {};
    const program = source.program || {};
    const variant = source.variant || {};
    const round = source.round || {};
    const form = round.form_template_id || source.form_template_id ||
      (round.form_template && round.form_template.id) || '';
    return {
      program_name: text(source.program_name || program.name || '未命名補助'),
      variant_name: text(source.variant_name || variant.name),
      round_name: text(source.round_name || round.name),
      form_template_id: text(form),
    };
  }

  function initialProgress(tasks) {
    const progress = {};
    tasks.forEach(task => {
      progress[task.id] = {completed: false, submitted: false, filled: false};
    });
    return progress;
  }

  function get(id) {
    if (!id) return null;
    const found = readEnvelope().applications.find(item => item && item.id === id);
    return found ? clone(found) : null;
  }

  function list(options) {
    const opts = options || {};
    let rows = readEnvelope().applications.filter(item => item && typeof item === 'object');
    if (opts.status) rows = rows.filter(item => item.status === opts.status);
    rows.sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')));
    return clone(rows);
  }

  function listActive() { return list({status: 'active'}); }

  function saveRecord(record) {
    const envelope = readEnvelope();
    const index = envelope.applications.findIndex(item => item && item.id === record.id);
    if (index >= 0) envelope.applications[index] = record;
    else envelope.applications.push(record);
    return writeEnvelope(envelope);
  }

  function start(context) {
    const ids = contextIds(context);
    const scope = scopeKey(context);
    const envelope = readEnvelope();
    const existing = envelope.applications.find(item => item && item.scope_key === scope && item.status === 'active');
    if (existing) return clone(existing);

    const tasks = taskList(context);
    const labels = displayContext(context);
    const timestamp = now();
    const record = {
      id: newId(),
      scope_key: scope,
      program_id: ids.program_id,
      variant_id: ids.variant_id,
      round_id: ids.round_id,
      program_name: labels.program_name,
      variant_name: labels.variant_name,
      round_name: labels.round_name,
      form_template_id: labels.form_template_id,
      items: tasks,
      progress: initialProgress(tasks),
      status: 'active',
      created_at: timestamp,
      updated_at: timestamp,
      completed_at: null,
    };
    envelope.applications.push(record);
    if (!writeEnvelope(envelope)) return null;
    return clone(record);
  }

  function taskState(record, task) {
    if (!task || !task.id) return {completed: false, submitted: false, filled: false, complete: false};
    const progress = record && record.progress && record.progress[task.id];
    const state = Object.assign({completed: false, submitted: false, filled: false}, progress || {});
    const type = normaliseType(task.status_type);
    const complete = type === 'form_submission'
      ? Boolean(state.filled && state.submitted)
      : type === 'submission' ? Boolean(state.submitted) : Boolean(state.completed);
    return {completed: Boolean(state.completed), submitted: Boolean(state.submitted), filled: Boolean(state.filled), complete};
  }

  function allItems(record) {
    return Array.isArray(record && record.items) ? record.items : [];
  }

  function dependenciesMet(record, task) {
    if (!task) return false;
    return (task.depends_on || []).every(id => {
      const dependency = allItems(record).find(item => item.id === id);
      return dependency ? taskState(record, dependency).complete : true;
    });
  }

  function progress(record) {
    const items = allItems(record);
    const completed = items.filter(task => taskState(record, task).complete).length;
    return {completed, total: items.length, percent: items.length ? Math.round(completed * 100 / items.length) : 0};
  }

  function nextTask(record) {
    const items = allItems(record);
    const available = items.find(task => !taskState(record, task).complete && dependenciesMet(record, task));
    if (available) return clone(available);
    return clone(items.find(task => !taskState(record, task).complete) || null);
  }

  function updateTask(id, taskId, patch) {
    const envelope = readEnvelope();
    const record = envelope.applications.find(item => item && item.id === id);
    if (!record || record.status !== 'active') return null;
    const task = allItems(record).find(item => item.id === taskId);
    if (!task) return null;
    const current = Object.assign({completed: false, submitted: false, filled: false}, record.progress && record.progress[taskId]);
    const input = isObject(patch) ? patch : {};
    ['completed', 'submitted', 'filled'].forEach(key => {
      if (Object.prototype.hasOwnProperty.call(input, key)) current[key] = Boolean(input[key]);
    });
    record.progress = record.progress || {};
    record.progress[taskId] = current;
    record.updated_at = now();
    if (!saveRecord(record)) return null;
    return clone(record);
  }

  function update(id, patch) {
    const envelope = readEnvelope();
    const record = envelope.applications.find(item => item && item.id === id);
    if (!record || record.status !== 'active') return null;
    const input = isObject(patch) ? patch : {};
    if (isObject(input.progress)) record.progress = clone(input.progress);
    record.updated_at = now();
    if (!saveRecord(record)) return null;
    return clone(record);
  }

  function canComplete(record) {
    const items = allItems(record);
    return items.length > 0 && items.every(task => taskState(record, task).complete);
  }

  function complete(id) {
    const envelope = readEnvelope();
    const record = envelope.applications.find(item => item && item.id === id);
    if (!record || record.status !== 'active' || !canComplete(record)) return null;
    record.status = 'completed';
    record.updated_at = now();
    record.completed_at = record.updated_at;
    if (!saveRecord(record)) return null;
    return clone(record);
  }

  function remove(id) {
    const envelope = readEnvelope();
    const next = envelope.applications.filter(item => !item || item.id !== id);
    if (next.length === envelope.applications.length) return false;
    envelope.applications = next;
    return writeEnvelope(envelope);
  }

  function requiredFieldsComplete(template, values) {
    const fields = template && Array.isArray(template.fields) ? template.fields : [];
    return fields.filter(field => field.required !== false && field.required).every(field => {
      const value = values && values[field.field_key];
      return value !== undefined && value !== null && String(value).trim() !== '';
    });
  }

  return Object.freeze({
    STORAGE_KEY,
    VERSION,
    STATUS_TYPES,
    contextIds,
    scopeKey,
    taskList,
    start,
    get,
    list,
    listActive,
    progress,
    taskState,
    dependenciesMet,
    nextTask,
    update,
    updateTask,
    canComplete,
    complete,
    remove,
    requiredFieldsComplete,
  });
});
