"""The map manifest: the labels people give each map (PROJECT_SCOPE.md Section 5.5).

It is a plain CSV so it stays inspectable and easy to back up, but it is normally edited
through the "Label maps" screen. The pipeline itself only adds rows for new maps, adds
columns that are new, and fills in the `file_id` that ties a row to its map. It never
changes a label.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

COLUMNS = (
    "file_id",
    "file_name",
    "revisit",
    "region_key",
    "footprint",
    "min_lon",
    "min_lat",
    "max_lon",
    "max_lat",
    "title",
    "notes",
)
BOX_FIELDS = ("min_lon", "min_lat", "max_lon", "max_lat")
# the fields the label screen may change
EDITABLE = ("revisit", "region_key", "footprint", *BOX_FIELDS, "title", "notes")

# How a map's footprint (the shape drawn on the globe) is decided:
#   places  a rectangle around the places it is tagged with
#   own     its own rectangle, from the four box columns
#   none    tagged only; nothing is drawn yet
# Blank means "own if the four box columns are filled, otherwise places" (rows from before
# this column existed).
FOOTPRINT_MODES = ("places", "own", "none")

_NOT_FLAGGED = {"", "no", "n", "false", "0"}


def is_flagged(row: dict) -> bool:
    """True if the row is marked as one to come back to (anything typed except no/false/0)."""
    return row.get("revisit", "").strip().lower() not in _NOT_FLAGGED


def footprint_mode(row: dict) -> str:
    """One of FOOTPRINT_MODES, or "" when the row does not say."""
    value = row.get("footprint", "").strip().lower()
    return value if value in FOOTPRINT_MODES else ""


def split_regions(value: str) -> list[str]:
    """Region keys from a manifest cell: lower-case, separated by semicolons."""
    return [key.strip().lower() for key in (value or "").split(";") if key.strip()]


def _read(path: Path) -> tuple[list[str], list[dict]]:
    """Header and rows of a hand-editable CSV, with stray spaces removed. Missing file: empty."""
    if not path.is_file():
        return [], []
    # utf-8-sig tolerates the byte-order mark spreadsheet apps add
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [(name or "").strip() for name in reader.fieldnames or []]
    rows = [{(k or "").strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]
    return header, rows


def _write(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, restval="", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _full_header(header: list[str]) -> list[str]:
    """Our columns first, then any extra columns someone added by hand."""
    return list(COLUMNS) + [name for name in header if name not in COLUMNS]


def load_manifest(manifest_path: Path) -> list[dict]:
    return [row for row in _read(manifest_path)[1] if row.get("file_id") or row.get("file_name")]


def load_regions(regions_path: Path) -> dict[str, dict]:
    """Region rows keyed by lower-case region_key."""
    return {row["region_key"].lower(): row for row in _read(regions_path)[1] if row.get("region_key")}


def find_row(rows: list[dict], file_id: str, file_name: str) -> dict | None:
    """The manifest row for a map: by file_id, else a row with that name and no file_id yet."""
    by_name = None
    for row in rows:
        if row.get("file_id") == file_id:
            return row
        if not row.get("file_id") and row.get("file_name") == file_name:
            by_name = row  # if a name appears twice, the last row wins
    return by_name


def sync_manifest(manifest_path: Path, maps: list[tuple[str, str]]) -> int:
    """Make sure every map (file_id, file_name) has a row. Returns how many rows were added.

    Rows written before `file_id` existed are tied to their map by name, when exactly one
    unclaimed map has that name.
    """
    header, rows = _read(manifest_path)
    changed = header != _full_header(header)

    claimed = {row["file_id"] for row in rows if row.get("file_id")}
    for row in rows:
        if row.get("file_id"):
            continue
        candidates = [fid for fid, name in maps if name == row.get("file_name") and fid not in claimed]
        if len(candidates) == 1:
            row["file_id"] = candidates[0]
            claimed.add(candidates[0])
            changed = True

    added = 0
    for file_id, file_name in sorted(maps, key=lambda m: (m[1], m[0])):
        if file_id not in claimed:
            rows.append({"file_id": file_id, "file_name": file_name})
            claimed.add(file_id)
            added += 1

    if changed or added:
        _write(manifest_path, _full_header(header), rows)
    return added


def update_rows(manifest_path: Path, changes: dict[str, dict]) -> int:
    """Apply label changes from the label screen. `changes` maps file_id -> new field values.

    Only the EDITABLE fields can be set. Returns how many rows were changed.
    """
    header, rows = _read(manifest_path)
    by_id = {row.get("file_id"): row for row in rows}
    updated = 0
    for file_id, fields in changes.items():
        row = by_id.get(file_id)
        if row is None:
            continue
        new_values = {name: str(fields[name]).strip() for name in EDITABLE if name in fields}
        if any(row.get(name, "") != value for name, value in new_values.items()):
            row.update(new_values)
            updated += 1
    if updated:
        _write(manifest_path, _full_header(header), rows)
    return updated
