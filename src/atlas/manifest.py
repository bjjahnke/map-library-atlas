"""The hand-edited map manifest (PROJECT_SCOPE.md Section 5.5).

The pipeline only ever adds blank rows for new files and blank columns that are new.
What you typed is never changed.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

COLUMNS = ("file_name", "revisit", "region_key", "min_lon", "min_lat", "max_lon", "max_lat", "title", "notes")

_NOT_FLAGGED = {"", "no", "n", "false", "0"}


def is_flagged(row: dict) -> bool:
    """True if the row is marked as one to come back to (anything typed except no/false/0)."""
    return row.get("revisit", "").strip().lower() not in _NOT_FLAGGED


def _add_missing_columns(manifest_path: Path) -> None:
    """Add any columns introduced since the file was created, keeping every existing cell."""
    text = manifest_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = reader.fieldnames or []
    if not header or all(column in header for column in COLUMNS):
        return
    rows = list(reader)
    new_header = list(COLUMNS) + [column for column in header if column not in COLUMNS]
    with open(manifest_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=new_header, restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def ensure_manifest(manifest_path: Path, file_names: list[str]) -> int:
    """Make sure every file has a row in the manifest. Returns how many rows were added."""
    known: set[str] = set()
    needs_newline = False
    if manifest_path.is_file():
        _add_missing_columns(manifest_path)
        text = manifest_path.read_text(encoding="utf-8-sig")
        known = {row.get("file_name", "") for row in csv.DictReader(text.splitlines())}
        needs_newline = bool(text) and not text.endswith("\n")

    missing = sorted(set(file_names) - known)
    if not missing and manifest_path.is_file():
        return 0

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not manifest_path.is_file() or manifest_path.stat().st_size == 0
    with open(manifest_path, "a", newline="") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(COLUMNS)
        elif needs_newline:
            fh.write("\n")
        for name in missing:
            writer.writerow([name] + [""] * (len(COLUMNS) - 1))
    return len(missing)


def _read_rows(path: Path) -> list[dict]:
    """Rows of a hand-edited CSV, with stray spaces removed. A missing file is just empty."""
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [
            {(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(fh)
        ]


def load_manifest(manifest_path: Path) -> dict[str, dict]:
    """Manifest rows keyed by file name. If a name appears twice, the last row wins."""
    return {row["file_name"]: row for row in _read_rows(manifest_path) if row.get("file_name")}


def load_regions(regions_path: Path) -> dict[str, dict]:
    """Region rows keyed by lower-case region_key."""
    return {row["region_key"].lower(): row for row in _read_rows(regions_path) if row.get("region_key")}
