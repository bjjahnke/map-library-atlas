"""The local web app behind `atlas view`: the globe, the label screen, and their data.

Listens on 127.0.0.1 only. Serves the static viewer, the gold GeoJSON, and a small JSON API:

    GET  /api/state            every map with its labels and status, plus the list of places
    POST /api/save             apply label changes, rebuild, return the new state
    POST /api/add?name=&path=  add one map to the library (the request body is the file)
    POST /api/rebuild          rebuild after adding maps, return the new state
    GET  /api/thumb/<file_id>  a small preview image of a map
    GET  /api/file/<file_id>   the map file itself
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import duckdb

from atlas import library, pipeline
from atlas.config import library_dir, manifest_csv, regions_csv
from atlas.manifest import (
    BOX_FIELDS,
    FOOTPRINT_MODES,
    find_row,
    footprint_mode,
    is_flagged,
    load_manifest,
    load_regions,
    split_regions,
    update_rows,
)

VIEWER_DIR = Path(__file__).resolve().parents[2] / "viewer"
THUMBNAIL_SIZE = 500
_save_lock = threading.Lock()
_thumbnail_lock = threading.Lock()


def load_state(config: dict) -> dict:
    """Everything the label screen shows."""
    where = pipeline.paths(config)
    with duckdb.connect(str(where["db"]), read_only=True) as con:
        rows = con.execute(
            "SELECT DISTINCT b.file_id, b.file_name, s.title, s.format, s.status, s.status_detail, "
            "s.bbox_source, s.bbox_precision "
            "FROM bronze.file_inventory b JOIN silver.maps s ON s.map_id = b.file_id "
            "ORDER BY b.file_name, b.file_id"
        ).fetchall()
    manifest = load_manifest(manifest_csv(config))
    maps = []
    for file_id, file_name, title, fmt, status, detail, source, precision in rows:
        manual = find_row(manifest, file_id, file_name) or {}
        maps.append(
            {
                "id": file_id,
                "file_name": file_name,
                "title": title,  # what is shown on the globe
                "custom_title": manual.get("title", ""),  # blank means "use the file name"
                "regions": split_regions(manual.get("region_key", "")),
                "revisit": is_flagged(manual),
                "notes": manual.get("notes", ""),
                # how the shape on the globe is decided: places | own | none
                "footprint": footprint_mode(manual)
                or ("own" if all(manual.get(field) for field in BOX_FIELDS) else "places"),
                "box": [manual.get(field, "") for field in BOX_FIELDS],  # west, south, east, north
                "format": fmt,
                "status": status,
                "status_detail": detail,
                "bbox_source": source,
                "bbox_precision": precision,
            }
        )
    regions = [
        {"key": key, "name": row.get("region_name") or key}
        for key, row in load_regions(regions_csv(config)).items()
    ]
    return {"maps": maps, "regions": regions}


def save_labels(config: dict, changes: dict) -> dict:
    """Write label changes to the manifest, rebuild, and return the new state."""
    cleaned = {}
    for file_id, fields in changes.items():
        if not isinstance(fields, dict):
            continue
        row = {}
        if "title" in fields:
            row["title"] = str(fields["title"])
        if "notes" in fields:
            row["notes"] = str(fields["notes"])
        if "revisit" in fields:
            row["revisit"] = "yes" if fields["revisit"] else ""
        if fields.get("footprint") in FOOTPRINT_MODES:
            row["footprint"] = fields["footprint"]
        if isinstance(fields.get("box"), list) and len(fields["box"]) == len(BOX_FIELDS):
            row |= {name: str(value).strip() for name, value in zip(BOX_FIELDS, fields["box"])}
        if "regions" in fields:
            row["region_key"] = "; ".join(split_regions(";".join(map(str, fields["regions"]))))
        cleaned[str(file_id)] = row
    with _save_lock:
        updated = update_rows(manifest_csv(config), cleaned)
        summary = pipeline.run(config)
    return load_state(config) | {"updated": updated, "on_globe": summary["gold"]["located"]}


def rebuild(config: dict) -> dict:
    with _save_lock:
        summary = pipeline.run(config)
    return load_state(config) | {"on_globe": summary["gold"]["located"]}


def add_upload(config: dict, body, length: int, name: str, relative_path: str) -> str:
    """Save an uploaded map into the library. Returns "added", "already" or "not_map"."""
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "upload"
        with open(staged, "wb") as fh:
            remaining = length
            while remaining > 0:
                chunk = body.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("the upload was cut short")
                fh.write(chunk)
                remaining -= len(chunk)
        origin = f"added from the browser: {relative_path or name}"
        return library.add_file(staged, name, origin, library_dir(config))


def _library_file(config: dict, file_id: str) -> Path | None:
    with duckdb.connect(str(pipeline.paths(config)["db"]), read_only=True) as con:
        found = con.execute(
            "SELECT file_path FROM bronze.file_inventory WHERE file_id = ? LIMIT 1", [file_id]
        ).fetchone()
    path = Path(found[0]) if found else None
    return path if path and path.is_file() else None


def thumbnail(config: dict, file_id: str) -> Path | None:
    """A cached PNG preview, made with macOS Quick Look. None if it cannot be made."""
    cache = pipeline.paths(config)["thumbnails"] / f"{file_id}.png"
    if cache.is_file():
        return cache
    source = _library_file(config, file_id)
    if source is None or shutil.which("qlmanage") is None:
        return None
    with _thumbnail_lock:  # one at a time; Quick Look is heavy
        if cache.is_file():
            return cache
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(
                    ["qlmanage", "-t", "-s", str(THUMBNAIL_SIZE), "-o", tmp, str(source)],
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            made = Path(tmp) / f"{source.name}.png"
            if not made.is_file():
                return None
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(made), cache)
    return cache


class AtlasHandler(http.server.BaseHTTPRequestHandler):
    config: dict = {}

    def log_message(self, format, *args):  # keep the terminal quiet
        pass

    # --- helpers
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _file(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self._send(404, b"Not found", "text/plain")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), content_type)

    def _is_local_request(self) -> bool:
        """Refuse requests sent to this server by pages from other websites."""
        allowed = {f"http://{host}:{self.server.server_port}" for host in ("127.0.0.1", "localhost")}
        origin = self.headers.get("Origin")
        return origin is None or origin in allowed

    # --- routes
    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/viewer"):
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers()
        elif path == "/viewer/":
            self._file(VIEWER_DIR / "index.html")
        elif path.startswith("/viewer/"):
            target = (VIEWER_DIR / path[len("/viewer/") :]).resolve()
            self._file(target if VIEWER_DIR in target.parents else None)
        elif path == "/data/gold/map_library.geojson":
            self._file(pipeline.paths(self.config)["geojson"])
        elif path == "/api/state":
            self._json(load_state(self.config))
        elif path.startswith("/api/thumb/"):
            self._file(thumbnail(self.config, path.rsplit("/", 1)[-1]))
        elif path.startswith("/api/file/"):
            self._file(_library_file(self.config, path.rsplit("/", 1)[-1]))
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if url.path not in ("/api/save", "/api/add", "/api/rebuild"):
            self._send(404, b"Not found", "text/plain")
            return
        if not self._is_local_request():
            self._json({"error": "requests from other sites are not accepted"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if url.path == "/api/add":
                query = parse_qs(url.query)
                name = query.get("name", [""])[0]
                if not name:
                    raise ValueError("no file name given")
                result = add_upload(self.config, self.rfile, length, name, query.get("path", [""])[0])
                self._json({"name": name, "result": result})
            elif url.path == "/api/rebuild":
                self.rfile.read(length)
                self._json(rebuild(self.config))
            else:
                changes = json.loads(self.rfile.read(length) or b"{}").get("changes", {})
                if not isinstance(changes, dict):
                    raise ValueError("changes must be an object")
                self._json(save_labels(self.config, changes))
        except (ValueError, AttributeError, OSError) as exc:
            self._json({"error": f"could not handle the request: {exc}"}, 400)


def make_server(config: dict, port: int) -> http.server.ThreadingHTTPServer:
    """Rebuild once so the atlas is current, then return a server ready to serve_forever()."""
    pipeline.run(config)
    handler = type("ConfiguredAtlasHandler", (AtlasHandler,), {"config": config})
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
