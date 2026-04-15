#!/usr/bin/env python3
"""Local web UI for generating WordPress WXR inventory imports.

Features:
- Bulk CSV upload -> WXR download
- Single-part form -> WXR download

Run:
    python3 inventory_ui.py --host 127.0.0.1 --port 8787
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from csv_to_wxr import create_wxr, indent_xml

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Inventory Import UI</title>
  <style>
    :root { --bg: #0b1020; --card: #111833; --text: #e9eefb; --accent: #4f8cff; --muted: #9db0dd; }
    body { margin:0; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: linear-gradient(180deg, #0b1020, #0d1430); color: var(--text); }
    .wrap { max-width: 980px; margin: 32px auto; padding: 0 16px; }
    .card { background: var(--card); border: 1px solid #26345f; border-radius: 12px; padding: 20px; margin-bottom: 18px; }
    h1,h2 { margin-top: 0; }
    p { color: var(--muted); }
    label { display:block; font-weight: 600; margin: 12px 0 6px; }
    input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #32426f; border-radius: 8px; padding: 10px; background: #0d1738; color: var(--text); }
    textarea { min-height: 90px; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .btn { margin-top: 14px; background: var(--accent); border: 0; color: white; padding: 11px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; }
    .help { font-size: 0.92rem; color: var(--muted); }
    .code { background:#0a132f; border:1px solid #22355f; padding: 10px; border-radius: 8px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Inventory Import UI</h1>
      <p>Quickly create WordPress WXR files for bulk CSV imports or single-part updates.</p>
      <p class="help">Upload the generated WXR in WordPress: <strong>Tools → Import → WordPress</strong>.</p>
    </div>

    <div class="card">
      <h2>Bulk CSV → WXR</h2>
      <form method="post" action="/bulk" enctype="multipart/form-data">
        <div class="grid">
          <div>
            <label>Site URL</label>
            <input name="site_url" value="https://logicnetworks.com" required />
          </div>
          <div>
            <label>CPT Slug</label>
            <input name="cpt" value="inventory_item" required />
          </div>
        </div>
        <div class="grid">
          <div>
            <label>Base Path</label>
            <input name="base_path" value="inventory" required />
          </div>
          <div>
            <label>Post Status</label>
            <input name="post_status" value="draft" required />
          </div>
        </div>
        <label>CSV File</label>
        <input type="file" name="csv_file" accept=".csv,text/csv" required />
        <p class="help">Expected headers include: Model, Description, Quantity (Condition optional).</p>
        <button class="btn" type="submit">Generate WXR from CSV</button>
      </form>
    </div>

    <div class="card">
      <h2>Single Part → WXR</h2>
      <form method="post" action="/single">
        <div class="grid">
          <div>
            <label>Site URL</label>
            <input name="site_url" value="https://logicnetworks.com" required />
          </div>
          <div>
            <label>CPT Slug</label>
            <input name="cpt" value="inventory_item" required />
          </div>
        </div>
        <div class="grid">
          <div>
            <label>Base Path</label>
            <input name="base_path" value="inventory" required />
          </div>
          <div>
            <label>Post Status</label>
            <input name="post_status" value="draft" required />
          </div>
        </div>

        <label>Model</label>
        <input name="Model" placeholder="Nokia G-240G-A" required />
        <label>Description</label>
        <textarea name="Description" placeholder="Short part description" required></textarea>

        <div class="grid">
          <div>
            <label>Quantity</label>
            <input name="Quantity" placeholder="12" required />
          </div>
          <div>
            <label>Condition</label>
            <input name="Condition" value="Used-Tested" />
          </div>
        </div>

        <label>Extra specs (JSON object)</label>
        <textarea name="specs_json" placeholder='{"Manufacturer":"Nokia","Port Count":"4"}'></textarea>
        <p class="help">Any key/value pairs here are added to the Technical Specifications table.</p>
        <button class="btn" type="submit">Generate Single-Part WXR</button>
      </form>
    </div>

    <div class="card">
      <h2>Run Locally</h2>
      <div class="code">python3 inventory_ui.py --host 127.0.0.1 --port 8787</div>
      <p class="help">Then open <strong>http://127.0.0.1:8787</strong> in your browser.</p>
    </div>
  </div>
</body>
</html>
"""


def _read_csv_dicts(file_bytes: bytes) -> list[dict[str, str]]:
    content = file_bytes.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV appears to have no header row.")

    required = {"Model", "Description", "Quantity"}
    missing = sorted(col for col in required if col not in set(reader.fieldnames))
    if missing:
        raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")

    rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no data rows.")
    return rows


def _wxr_bytes(rows: list[dict[str, str]], *, site_url: str, base_path: str, cpt: str, post_status: str) -> bytes:
    tree = create_wxr(
        rows,
        site_url=site_url,
        base_path=base_path,
        cpt=cpt,
        title_column="Model",
        description_column="Description",
        quantity_column="Quantity",
        condition_column="Condition" if any("Condition" in r for r in rows) else None,
        default_condition="Used-Tested",
        post_status=post_status,
    )
    indent_xml(tree.getroot())
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return output.getvalue()


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return cleaned or "inventory"


def _decode_multipart(handler: BaseHTTPRequestHandler) -> dict[str, str | bytes]:
    ctype = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        raise ValueError("Expected multipart form data.")

    boundary_match = re.search(r"boundary=(.+)", ctype)
    if not boundary_match:
        raise ValueError("Missing multipart boundary.")
    boundary = boundary_match.group(1).encode("utf-8")

    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length)

    result: dict[str, str | bytes] = {}
    for part in body.split(b"--" + boundary):
        if not part or part in {b"--\r\n", b"--"}:
            continue
        header_blob, _, payload = part.partition(b"\r\n\r\n")
        if not payload:
            continue

        headers = header_blob.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        field_name = name_match.group(1)

        payload = payload.rstrip(b"\r\n")
        if 'filename="' in headers:
            result[field_name] = payload
        else:
            result[field_name] = payload.decode("utf-8", errors="replace")
    return result


class InventoryUIHandler(BaseHTTPRequestHandler):
    server_version = "InventoryUI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        payload = HTML_PAGE.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/bulk":
                self._handle_bulk()
                return
            if self.path == "/single":
                self._handle_single()
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:  # noqa: BLE001 - user-facing server errors
            self._send_text(str(exc), HTTPStatus.BAD_REQUEST)

    def _handle_bulk(self) -> None:
        form = _decode_multipart(self)
        site_url = str(form.get("site_url", "")).strip()
        cpt = str(form.get("cpt", "inventory_item")).strip() or "inventory_item"
        base_path = str(form.get("base_path", "inventory")).strip() or "inventory"
        post_status = str(form.get("post_status", "draft")).strip() or "draft"

        csv_bytes = form.get("csv_file")
        if not isinstance(csv_bytes, bytes):
            raise ValueError("CSV file upload is required.")

        rows = _read_csv_dicts(csv_bytes)
        wxr = _wxr_bytes(rows, site_url=site_url, base_path=base_path, cpt=cpt, post_status=post_status)

        fname = f"inventory-bulk-{_sanitize_filename(base_path)}.xml"
        self._send_download(wxr, fname)

    def _handle_single(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form_qs = parse_qs(body, keep_blank_values=True)
        form = {k: v[0] for k, v in form_qs.items()}

        site_url = form.get("site_url", "").strip()
        cpt = form.get("cpt", "inventory_item").strip() or "inventory_item"
        base_path = form.get("base_path", "inventory").strip() or "inventory"
        post_status = form.get("post_status", "draft").strip() or "draft"

        model = form.get("Model", "").strip()
        description = form.get("Description", "").strip()
        quantity = form.get("Quantity", "").strip()
        condition = form.get("Condition", "Used-Tested").strip() or "Used-Tested"

        if not site_url:
            raise ValueError("Site URL is required.")
        if not model:
            raise ValueError("Model is required.")
        if not description:
            raise ValueError("Description is required.")
        if not quantity:
            raise ValueError("Quantity is required.")

        row: dict[str, str] = {
            "Model": model,
            "Description": description,
            "Quantity": quantity,
            "Condition": condition,
        }

        specs_raw = form.get("specs_json", "").strip()
        if specs_raw:
            try:
                extra = json.loads(specs_raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid specs JSON: {exc.msg}") from exc
            if not isinstance(extra, dict):
                raise ValueError("Specs JSON must be an object of key/value pairs.")
            for key, value in extra.items():
                row[str(key)] = str(value)

        wxr = _wxr_bytes([row], site_url=site_url, base_path=base_path, cpt=cpt, post_status=post_status)
        fname = f"single-part-{_sanitize_filename(model)}.xml"
        self._send_download(wxr, fname)

    def _send_download(self, payload: bytes, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, text: str, status: HTTPStatus) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local UI for generating inventory WXR files.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8787, help="Port number (default: 8787)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), InventoryUIHandler)
    print(f"Inventory UI running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
