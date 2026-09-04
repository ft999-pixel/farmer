from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import sqlite3, json, os, uuid, datetime

DB = 'data/form.db'
UPLOAD = 'data/uploads'
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
CORS(app)

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c

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
            pdf_path TEXT NOT NULL,
            effective_from TEXT,
            created_at TEXT DEFAULT (datetime('now'))
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
            prefill_source TEXT
        );
        CREATE TABLE IF NOT EXISTS applications(
            id TEXT PRIMARY KEY,
            template_version_id TEXT NOT NULL REFERENCES template_versions(id),
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT (datetime('now')),
            data_json TEXT NOT NULL
        );
        ''')
        c.commit()

init_db()

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
        return jsonify([dict(r) for r in rows])

@app.get('/api/template-versions/<vid>/fields')
def list_fields(vid):
    with db() as c:
        rows = c.execute('SELECT * FROM form_fields WHERE template_version_id=? ORDER BY page, pos_y, pos_x', (vid,)).fetchall()
        return jsonify([dict(r) for r in rows])

@app.post('/api/templates')
def create_template():
    data = request.get_json(force=True)
    tid = str(uuid.uuid4())
    vid = str(uuid.uuid4())
    pdf_filename = tid + '.pdf'
    pdf_path = os.path.join(UPLOAD, pdf_filename)
    if data.get('pdf_base64'):
        import base64
        open(pdf_path, 'wb').write(base64.b64decode(data['pdf_base64'].split(',')[-1]))
    fields = data.get('fields', [])
    with db() as c:
        c.execute('INSERT INTO templates VALUES (?,?,?,?)', (tid, data['name'], data.get('subsidy_id'), vid))
        c.execute('INSERT INTO template_versions VALUES (?,?,?,?,?,?)',
                  (vid, tid, '1.0', pdf_path, datetime.date.today().isoformat(), datetime.datetime.now().isoformat()))
        for f in fields:
            fid = str(uuid.uuid4())
            c.execute('''INSERT INTO form_fields (id,template_version_id,field_key,label,type,page,pos_x,pos_y,width,height,required,editable,prefill_source)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (fid, vid, f['field_key'], f['label'], f['type'], f.get('page',1),
                       f.get('pos_x',50), f.get('pos_y',50), f.get('width',200), f.get('height',20),
                       1 if f.get('required') else 0, 1 if f.get('editable', True) else 0, f.get('prefill_source')))
        c.commit()
    return jsonify({'template_id': tid, 'version_id': vid})

@app.get('/api/template-versions/<vid>/pdf')
def get_pdf(vid):
    with db() as c:
        row = c.execute('SELECT pdf_path FROM template_versions WHERE id=?', (vid,)).fetchone()
        if not row or not os.path.exists(row['pdf_path']):
            return jsonify({'error': 'not found'}), 404
        return send_file(row['pdf_path'], as_attachment=False, mimetype='application/pdf')

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
