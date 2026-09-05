#!/usr/bin/env python3
"""Convert afa115_templates.json entries to farmer /api/templates payloads.

This intentionally does not upload private application values.
Coordinates must be calibrated before POSTing.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "afa115_templates.json").read_text(encoding="utf-8"))

for t in data["templates"]:
    payload = {
        "name": t["name"],
        "subsidy_id": t["subsidy_id"],
        "version": t["version"],
        "source_pdf_url": t.get("source_pdf_url"),
        "source_page": t.get("source_page"),
        "source_page_index": t.get("source_page_index"),
        "usage": t.get("usage"),
        "fields": []
    }
    for f in t["fields"]:
        payload["fields"].append({
            "field_key": f["field_key"],
            "label": f["label"],
            "type": f.get("type", "text"),
            "required": f.get("required", False),
            "editable": f.get("editable", True),
            "prefill_source": f.get("prefill_source"),
            "note": f.get("note"),
            "privacy": f.get("privacy", "application_local"),
            "options": f.get("options", f.get("choices", [])),
            # The checked-in local PDF is a cropped one-page file. Keep the
            # original page in source_page for provenance, but target page 1
            # when the local file is used.
            "page": f.get("page") or t.get("pdf_page") or (
                1 if t.get("pdf_path") else t.get("source_page") or 1
            ),
            "pos_x": None,
            "pos_y": None,
            "width": None,
            "height": None,
            "coordinates_calibrated": False,
        })
    print(json.dumps(payload, ensure_ascii=False, indent=2))
