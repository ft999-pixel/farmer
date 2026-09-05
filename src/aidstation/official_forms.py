"""Read-only access to the checked-in official-form demo pack.

The pack contains extracted pages from the supplied Ministry of Agriculture
PDF, plus coordinates and privacy-aware prefill mappings.  This router keeps
the source files behind the existing FastAPI app so the static demo can use
them without inventing a paper form or exposing arbitrary filesystem paths.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = ROOT / "futuremode_official_forms_v2"
MANIFEST_PATH = PACK_DIR / "templates.json"
PDF_DIR = PACK_DIR / "pdfs"
TRACKED_MANIFEST_PATH = ROOT / "data" / "form_templates.json"
TRACKED_PDF_DIR = ROOT / "web" / "official-forms"

router = APIRouter(prefix="/official-forms", tags=["official-forms"])


def _manifest() -> dict:
    manifest_path = MANIFEST_PATH if MANIFEST_PATH.exists() else TRACKED_MANIFEST_PATH
    if not manifest_path.exists():
        return {"templates": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # ``data/form_templates.json`` is the compact checked-in fallback.  The
    # supplied pack remains the richer source when it is present locally.
    if manifest_path == TRACKED_MANIFEST_PATH:
        for template in manifest.get("templates", []):
            template.setdefault("pdf", template.get("official_pdf") or template.get("web_pdf"))
    return manifest


def _public_template(template: dict) -> dict:
    public = {k: v for k, v in template.items() if k != "fields"}
    public["fields"] = [
        {k: v for k, v in field.items() if k != "storage_scope"}
        for field in template.get("fields", [])
    ]
    pdf_name = Path(template.get("pdf") or template.get("official_pdf") or "").name
    if pdf_name:
        public["pdf_url"] = f"/official-forms/pdf/{pdf_name}"
    return public


@router.get("/manifest")
def get_manifest() -> dict:
    """Return template mappings; private values are never part of the manifest."""
    manifest = _manifest()
    public_templates = [_public_template(template)
                        for template in manifest.get("templates", [])]
    return {
        "schema": manifest.get("schema"),
        "policy": manifest.get("policy", "OFFICIAL_FORMS_ONLY"),
        "source_document": manifest.get("source_document", {}),
        "templates": public_templates,
    }


@router.get("/templates/{template_id:path}")
def get_template(template_id: str) -> dict:
    for template in _manifest().get("templates", []):
        if template.get("id") == template_id:
            return _public_template(template)
    raise HTTPException(404, "找不到官方表單模板")


@router.get("/pdf/{filename}")
def get_pdf(filename: str) -> FileResponse:
    # The manifest is the allow-list; callers cannot select another path.
    allowed = {
        Path(template.get("pdf", "")).name
        for template in _manifest().get("templates", [])
        if template.get("pdf")
    }
    if filename not in allowed:
        raise HTTPException(404, "找不到官方表單 PDF")
    path = PDF_DIR / filename
    if not path.is_file():
        path = TRACKED_PDF_DIR / filename
    if not path.is_file():
        raise HTTPException(404, "官方表單 PDF 尚未匯入")
    return FileResponse(path, media_type="application/pdf", filename=filename)
