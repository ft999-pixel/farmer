from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
import sqlite3, json, os, uuid, datetime

APP_DIR = Path(__file__).resolve().parent
DB = os.environ.get('PREFILL_DB', str(APP_DIR / 'data' / 'form.db'))
UPLOAD = os.environ.get('PREFILL_UPLOAD_DIR', str(APP_DIR / 'data' / 'uploads'))
AFA115_TEMPLATES = APP_DIR / 'afa115_form_templates' / 'afa115_templates.json'
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
CORS(app)

def db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c


def _ensure_column(c, table, column, definition):
    """Add a column when opening a database created by the original demo."""
    columns = {row['name'] for row in c.execute(f'PRAGMA table_info({table})')}
    if column not in columns:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


def _migrate_schema(c):
    # The first version of prefill only had the core fields below.  Keep old
    # local databases usable while adding the metadata used by AFA templates.
    _ensure_column(c, 'template_versions', 'source_pdf_url', 'TEXT')
    _ensure_column(c, 'template_versions', 'source_page', 'INTEGER')
    _ensure_column(c, 'template_versions', 'source_page_index', 'INTEGER')
    _ensure_column(c, 'template_versions', 'usage', 'TEXT')
    _ensure_column(c, 'form_fields', 'note', 'TEXT')
    _ensure_column(c, 'form_fields', 'privacy', "TEXT NOT NULL DEFAULT 'application_local'")
    _ensure_column(c, 'form_fields', 'options_json', 'TEXT')
    _ensure_column(c, 'form_fields', 'coordinates_calibrated', 'INTEGER NOT NULL DEFAULT 1')


def _load_afa115_templates(path=AFA115_TEMPLATES):
    """Read and lightly validate the checked-in AFA 115 template catalog."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    templates = data.get('templates')
    if not isinstance(templates, list):
        raise ValueError('AFA 115 template catalog must contain a templates list')
    for template in templates:
        for key in ('id', 'name', 'subsidy_id', 'version', 'fields'):
            if not template.get(key):
                raise ValueError(f'AFA 115 template is missing {key}: {template!r}')
        if not isinstance(template['fields'], list):
            raise ValueError(f'AFA 115 fields must be a list: {template["id"]}')
        field_keys = [field.get('field_key') for field in template['fields']]
        if any(not key for key in field_keys) or len(field_keys) != len(set(field_keys)):
            raise ValueError(f'AFA 115 fields must have unique field_key values: {template["id"]}')
    return templates


def _json_options(field):
    options = field.get('options', field.get('choices'))
    return json.dumps(options, ensure_ascii=False) if options is not None else None


def _number_or_default(value, default):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _seed_afa115_templates(c, templates):
    """Upsert catalog templates without touching user-created templates."""
    upload_dir = Path(UPLOAD)
    for template in templates:
        template_id = template['id']
        version = str(template['version'])
        version_id = f'{template_id}-v{version}'
        configured_pdf = template.get('pdf_path')
        pdf_path = Path(configured_pdf) if configured_pdf else upload_dir / f'{template_id}.pdf'
        if not pdf_path.is_absolute():
            pdf_path = upload_dir / pdf_path
        default_field_page = template.get(
            'pdf_page',
            1 if configured_pdf else template.get('source_page') or 1,
        )

        c.execute('''
            INSERT INTO templates (id, name, subsidy_id, current_version)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                subsidy_id=excluded.subsidy_id,
                current_version=excluded.current_version
        ''', (template_id, template['name'], template['subsidy_id'], version_id))
        c.execute('''
            INSERT INTO template_versions
                (id, template_id, version, pdf_path, effective_from,
                 source_pdf_url, source_page, source_page_index, usage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                template_id=excluded.template_id,
                version=excluded.version,
                pdf_path=excluded.pdf_path,
                source_pdf_url=excluded.source_pdf_url,
                source_page=excluded.source_page,
                source_page_index=excluded.source_page_index,
                usage=excluded.usage
        ''', (
            version_id,
            template_id,
            version,
            str(pdf_path),
            datetime.date.today().isoformat(),
            template.get('source_pdf_url'),
            template.get('source_page'),
            template.get('source_page_index'),
            template.get('usage'),
        ))

        field_ids = []
        for field in template['fields']:
            field_id = f'{version_id}:{field["field_key"]}'
            field_ids.append(field_id)
            has_coordinates = all(
                isinstance(field.get(key), (int, float)) and not isinstance(field.get(key), bool)
                for key in ('pos_x', 'pos_y', 'width', 'height')
            )
            c.execute('''
                INSERT INTO form_fields
                    (id, template_version_id, field_key, label, type, page,
                     pos_x, pos_y, width, height, required, editable,
                     prefill_source, note, privacy, options_json,
                     coordinates_calibrated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    template_version_id=excluded.template_version_id,
                    field_key=excluded.field_key,
                    label=excluded.label,
                    type=excluded.type,
                    page=excluded.page,
                    pos_x=excluded.pos_x,
                    pos_y=excluded.pos_y,
                    width=excluded.width,
                    height=excluded.height,
                    required=excluded.required,
                    editable=excluded.editable,
                    prefill_source=excluded.prefill_source,
                    note=excluded.note,
                    privacy=excluded.privacy,
                    options_json=excluded.options_json,
                    coordinates_calibrated=excluded.coordinates_calibrated
            ''', (
                field_id,
                version_id,
                field['field_key'],
                field['label'],
                field.get('type', 'text'),
                field.get('page') or default_field_page,
                _number_or_default(field.get('pos_x'), 50),
                _number_or_default(field.get('pos_y'), 50),
                _number_or_default(field.get('width'), 200),
                _number_or_default(field.get('height'), 20),
                1 if field.get('required') else 0,
                1 if field.get('editable', True) else 0,
                field.get('prefill_source'),
                field.get('note'),
                field.get('privacy', 'application_local'),
                _json_options(field),
                1 if field.get('coordinates_calibrated', has_coordinates) else 0,
            ))

        # Keep a re-run in sync if a checked-in catalog removes a field.
        if field_ids:
            placeholders = ','.join('?' for _ in field_ids)
            c.execute(
                f'DELETE FROM form_fields WHERE template_version_id=? AND id NOT IN ({placeholders})',
                [version_id, *field_ids],
            )


def seed_afa115_templates(path=AFA115_TEMPLATES):
    """Import the AFA 115 catalog into the configured prefill database."""
    templates = _load_afa115_templates(path)
    with db() as c:
        _seed_afa115_templates(c, templates)
        c.commit()
    return len(templates)


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS templates(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            subsidy_id TEXT,
            current_version TEXT
        );
        CREATE TABLE IF NOT EXISTS template_versions(
            id TEXT PRIMARY KEY,
            template_id TEXT NOT NULL REFERENCES templates(id),
            version TEXT NOT NULL,
            pdf_path TEXT NOT NULL DEFAULT '',
            effective_from TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            source_pdf_url TEXT,
            source_page INTEGER,
            source_page_index INTEGER,
            usage TEXT
        );
        CREATE TABLE IF NOT EXISTS form_fields(
            id TEXT PRIMARY KEY,
            template_version_id TEXT NOT NULL REFERENCES template_versions(id),
            field_key TEXT NOT NULL,
            label TEXT NOT NULL,
            type TEXT NOT NULL,
            page INTEGER NOT NULL DEFAULT 1,
            pos_x REAL NOT NULL DEFAULT 50,
            pos_y REAL NOT NULL DEFAULT 50,
            width REAL NOT NULL DEFAULT 200,
            height REAL NOT NULL DEFAULT 20,
            required INTEGER DEFAULT 0,
            editable INTEGER DEFAULT 1,
            prefill_source TEXT,
            note TEXT,
            privacy TEXT NOT NULL DEFAULT 'application_local',
            options_json TEXT,
            coordinates_calibrated INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS applications(
            id TEXT PRIMARY KEY,
            template_version_id TEXT NOT NULL REFERENCES template_versions(id),
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT (datetime('now')),
            data_json TEXT NOT NULL
        );
        ''')
        _migrate_schema(c)
        c.commit()
    if AFA115_TEMPLATES.exists():
        seed_afa115_templates()

init_db()


def _resolve_stored_pdf(path):
    if not path:
        return None
    candidate = Path(path)
    options = [candidate] if candidate.is_absolute() else [candidate, APP_DIR / candidate]
    return next((item for item in options if item.is_file()), None)


def _version_payload(row):
    payload = dict(row)
    pdf = _resolve_stored_pdf(payload.get('pdf_path'))
    payload['pdf_available'] = pdf is not None
    payload['pdf_url'] = f'/api/template-versions/{payload["id"]}/pdf'
    return payload


def _field_payload(row):
    payload = dict(row)
    raw_options = payload.get('options_json')
    if raw_options:
        try:
            payload['options'] = json.loads(raw_options)
        except json.JSONDecodeError:
            payload['options'] = []
    else:
        payload['options'] = []
    return payload

# ---------- Template API ----------
@app.get('/api/templates')
def list_templates():
    with db() as c:
        rows = c.execute('SELECT * FROM templates ORDER BY rowid DESC').fetchall()
        return jsonify([dict(r) for r in rows])

@app.get('/api/templates/<tid>/versions')
def list_versions(tid):
    with db() as c:
        rows = c.execute('SELECT * FROM template_versions WHERE template_id=? ORDER BY version DESC', (tid,)).fetchall()
        return jsonify([_version_payload(r) for r in rows])

@app.get('/api/template-versions/<vid>/fields')
def list_fields(vid):
    with db() as c:
        rows = c.execute('SELECT * FROM form_fields WHERE template_version_id=? ORDER BY page, pos_y, pos_x', (vid,)).fetchall()
        return jsonify([_field_payload(r) for r in rows])

@app.post('/api/templates')
def create_template():
    data = request.get_json(force=True)
    tid = str(uuid.uuid4())
    vid = str(uuid.uuid4())
    pdf_path = str(Path(UPLOAD) / f'{tid}.pdf')
    if data.get('pdf_base64'):
        import base64
        Path(pdf_path).write_bytes(base64.b64decode(data['pdf_base64'].split(',')[-1]))
    fields = data.get('fields', [])
    with db() as c:
        c.execute('INSERT INTO templates VALUES (?,?,?,?)', (tid, data['name'], data.get('subsidy_id'), vid))
        c.execute('''
            INSERT INTO template_versions
                (id, template_id, version, pdf_path, effective_from, created_at,
                 source_pdf_url, source_page, source_page_index, usage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            vid, tid, data.get('version', '1.0'), pdf_path,
            datetime.date.today().isoformat(), datetime.datetime.now().isoformat(),
            data.get('source_pdf_url'), data.get('source_page'),
            data.get('source_page_index'), data.get('usage'),
        ))
        for f in fields:
            fid = str(uuid.uuid4())
            c.execute('''INSERT INTO form_fields (id,template_version_id,field_key,label,type,page,pos_x,pos_y,width,height,required,editable,prefill_source)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (fid, vid, f['field_key'], f['label'], f['type'], f.get('page',1),
                       _number_or_default(f.get('pos_x'),50), _number_or_default(f.get('pos_y'),50),
                       _number_or_default(f.get('width'),200), _number_or_default(f.get('height'),20),
                       1 if f.get('required') else 0, 1 if f.get('editable', True) else 0, f.get('prefill_source')))
            c.execute('''UPDATE form_fields
                         SET note=?, privacy=?, options_json=?, coordinates_calibrated=?
                         WHERE id=?''', (
                             f.get('note'), f.get('privacy', 'application_local'),
                             _json_options(f),
                             1 if f.get('coordinates_calibrated', all(
                                 isinstance(f.get(k), (int, float)) and not isinstance(f.get(k), bool)
                                 for k in ('pos_x', 'pos_y', 'width', 'height')))
                             else 0,
                             fid))
        c.commit()
    return jsonify({'template_id': tid, 'version_id': vid})

@app.get('/api/template-versions/<vid>/pdf')
def get_pdf(vid):
    with db() as c:
        row = c.execute('SELECT pdf_path, source_pdf_url FROM template_versions WHERE id=?', (vid,)).fetchone()
        if not row:
            return jsonify({'error': 'not found'}), 404
        pdf = _resolve_stored_pdf(row['pdf_path'])
        if pdf:
            return send_file(pdf, as_attachment=False, mimetype='application/pdf')
        return jsonify({'error': '本機 PDF 尚未匯入'}), 404

@app.post('/api/applications')
def create_application():
    data = request.get_json(force=True)
    aid = str(uuid.uuid4())
    with db() as c:
        c.execute('INSERT INTO applications VALUES (?,?,?,?,?)',
                  (aid, data['template_version_id'], 'draft', datetime.datetime.now().isoformat(),
                   json.dumps(data.get('data', {}), ensure_ascii=False)))
        c.commit()
    return jsonify({'application_id': aid})

@app.post('/api/profiles')
def put_profile():
    data = request.get_json(force=True)
    key = data['key']
    value = data['value']
    # store in sqlite to avoid adding another DB layer for demo
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS profile_store(key TEXT PRIMARY KEY, value TEXT)')
        c.execute('INSERT INTO profile_store VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value, ensure_ascii=False)))
        c.commit()
    return jsonify({'ok': True})

@app.get('/api/profiles')
def get_profiles():
    with db() as c:
        rows = c.execute('SELECT key, value FROM profile_store').fetchall()
        return jsonify({r['key']: json.loads(r['value']) for r in rows})

@app.get('/api/applications/<aid>')
def get_application(aid):
    with db() as c:
        row = c.execute('SELECT * FROM applications WHERE id=?', (aid,)).fetchone()
        if not row:
            return jsonify({'error': 'not found'}), 404
        r = dict(row)
        r['data_json'] = json.loads(r['data_json'])
        return jsonify(r)

@app.patch('/api/applications/<aid>')
def patch_application(aid):
    data = request.get_json(force=True)
    with db() as c:
        current = c.execute('SELECT data_json FROM applications WHERE id=?', (aid,)).fetchone()
        if not current:
            return jsonify({'error': 'not found'}), 404
        merged = json.loads(current['data_json'])
        merged.update(data.get('data', {}))
        c.execute('UPDATE applications SET data_json=? WHERE id=?', (json.dumps(merged, ensure_ascii=False), aid))
        if data.get('status'):
            c.execute('UPDATE applications SET status=? WHERE id=?', (data['status'], aid))
        c.commit()
    return jsonify({'ok': True})

@app.get('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
