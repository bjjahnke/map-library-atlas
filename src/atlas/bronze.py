"""Bronze layer: the raw list of map files, exactly as found. Source files are only read.

`raw_metadata` holds whatever metadata is stored inside the file, as JSON (see metadata.py).
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from atlas.census import MAP_EXTENSIONS, iter_files
from atlas.metadata import read_raw_metadata

COLUMNS = (
    "file_id",
    "file_path",
    "file_name",
    "extension",
    "size_bytes",
    "modified_at",
    "ingested_at",
    "raw_metadata",
)

_CREATE = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE TABLE IF NOT EXISTS bronze.file_inventory (
    file_id      VARCHAR,              -- SHA-256 of contents; equal ids mean duplicate files
    file_path    VARCHAR PRIMARY KEY,
    file_name    VARCHAR,
    extension    VARCHAR,
    size_bytes   BIGINT,
    modified_at  TIMESTAMP,            -- UTC
    ingested_at  TIMESTAMP,            -- UTC
    raw_metadata JSON
);
"""


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_naive(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)


def build_inventory(folder: Path, db_path: Path) -> dict:
    """Record every map file under folder. Files whose size and date are unchanged are skipped."""
    if not folder.is_dir():
        raise NotADirectoryError(f"maps_folder does not exist or is not a folder: {folder}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    seen: set[str] = set()
    with duckdb.connect(str(db_path)) as con:
        con.execute(_CREATE)
        existing = {
            path: (size, modified)
            for path, size, modified in con.execute(
                "SELECT file_path, size_bytes, modified_at FROM bronze.file_inventory"
            ).fetchall()
        }
        # rows recorded before raw metadata was captured
        without_metadata = {
            path
            for (path,) in con.execute(
                "SELECT file_path FROM bronze.file_inventory WHERE raw_metadata IS NULL"
            ).fetchall()
        }
        ingested_at = _utc_naive(datetime.now(tz=timezone.utc).timestamp())

        for path in iter_files(folder):
            if path.suffix.lower() not in MAP_EXTENSIONS:
                continue
            file_path = str(path.resolve())
            seen.add(file_path)
            stat = path.stat()
            modified_at = _utc_naive(stat.st_mtime)
            if existing.get(file_path) == (stat.st_size, modified_at):
                counts["unchanged"] += 1
                if file_path in without_metadata:
                    con.execute(
                        "UPDATE bronze.file_inventory SET raw_metadata = ? WHERE file_path = ?",
                        [json.dumps(read_raw_metadata(path)), file_path],
                    )
                continue
            counts["changed" if file_path in existing else "new"] += 1
            con.execute(
                "INSERT OR REPLACE INTO bronze.file_inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    hash_file(path),
                    file_path,
                    path.name,
                    path.suffix.lower().lstrip("."),
                    stat.st_size,
                    modified_at,
                    ingested_at,
                    json.dumps(read_raw_metadata(path)),
                ],
            )
        total = con.execute("SELECT count(*) FROM bronze.file_inventory").fetchone()[0]

    # Rows are kept for files that have since been removed from the folder; just report them.
    return counts | {"total": total, "no_longer_in_folder": len(set(existing) - seen)}


def read_inventory(db_path: Path) -> list[dict]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            f"SELECT {', '.join(COLUMNS)} FROM bronze.file_inventory ORDER BY file_name, file_path"
        ).fetchall()
    return [dict(zip(COLUMNS, row)) for row in rows]


def _local(utc_naive: datetime) -> str:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def export_csv(db_path: Path, csv_path: Path) -> int:
    """Write the inventory as a spreadsheet-friendly CSV (times shown in local time)."""
    rows = read_inventory(db_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            row["modified_at"] = _local(row["modified_at"])
            row["ingested_at"] = _local(row["ingested_at"])
            writer.writerow(row)
    return len(rows)
