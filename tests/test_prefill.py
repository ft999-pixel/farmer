"""Integration tests for the standalone prefill service and AFA 115 catalog."""
import importlib.util
import json
from pathlib import Path

import pytest


PREFILL_DIR = Path(__file__).resolve().parents[1] / 'module' / 'prefill'
CATALOG = PREFILL_DIR / 'afa115_form_templates' / 'afa115_templates.json'


@pytest.fixture()
def prefill_app(tmp_path, monkeypatch):
    monkeypatch.setenv('PREFILL_DB', str(tmp_path / 'form.db'))
    monkeypatch.setenv('PREFILL_UPLOAD_DIR', str(tmp_path / 'uploads'))
    spec = importlib.util.spec_from_file_location('prefill_app_for_test', PREFILL_DIR / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_afa115_catalog_is_seeded_and_exposed(prefill_app):
    client = prefill_app.app.test_client()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))

    templates = client.get('/api/templates').get_json()
    assert [template['id'] for template in templates] == [
        'afa115-appendix-06',
        'afa115-appendix-09',
        'afa115-appendix-13',
        'afa115-appendix-18',
        'afa115-appendix-19',
    ][::-1]

    by_id = {template['id']: template for template in catalog['templates']}
    for template in templates:
        version = client.get(f"/api/templates/{template['id']}/versions").get_json()[0]
        fields = client.get(f"/api/template-versions/{version['id']}/fields").get_json()
        expected = by_id[template['id']]

        assert version['version'] == expected['version']
        assert version['source_page'] == expected['source_page']
        assert version['source_pdf_url'] == expected['source_pdf_url']
        assert version['pdf_path'] == str(Path(prefill_app.UPLOAD) / expected['pdf_path'])
        assert version['pdf_available'] is False
        assert {field['page'] for field in fields} == {expected['pdf_page']}
        assert [field['field_key'] for field in fields] == [
            field['field_key'] for field in expected['fields']
        ]

    id_count = len(templates)
    assert prefill_app.seed_afa115_templates() == id_count
    assert len(client.get('/api/templates').get_json()) == id_count


def test_local_pdf_is_preferred_over_source_url(prefill_app):
    client = prefill_app.app.test_client()
    template = client.get('/api/templates/afa115-appendix-06/versions').get_json()[0]
    pdf_path = Path(prefill_app.UPLOAD) / 'afa115-appendix-06.pdf'
    pdf_path.write_bytes(b'%PDF-test')

    version = client.get('/api/templates/afa115-appendix-06/versions').get_json()[0]
    assert version['pdf_available'] is True
    response = client.get(f"/api/template-versions/{template['id']}/pdf")
    assert response.status_code == 200
    assert response.data == b'%PDF-test'


def test_pdf_endpoint_does_not_fall_back_to_remote_source(prefill_app):
    client = prefill_app.app.test_client()
    version = client.get('/api/templates/afa115-appendix-06/versions').get_json()[0]

    response = client.get(f"/api/template-versions/{version['id']}/pdf")

    assert response.status_code == 404
    assert response.get_json() == {'error': '本機 PDF 尚未匯入'}
