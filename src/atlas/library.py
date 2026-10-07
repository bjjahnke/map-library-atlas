"""The library: one flat folder holding the atlas's own copy of every map.

`atlas add` copies maps in; the originals are only read. Each copy is named
`<original name>__<start of fingerprint>.<ext>` so different maps that share a name cannot
collide, and `index.csv` in the same folder remembers where each one came from.
"""

from __future__ import annotations

import csv
import shutil
import threading
from datetime import datetime
from pathlib import Path

from atlas.bronze import hash_file
from atlas.census import MAP_EXTENSIONS, iter_files

INDEX_NAME = "index.csv"
INDEX_COLUMNS = ("file_id", "library_name", "original_name", "original_path", "added_at")
_lock = threading.Lock()  # one add at a time, so the index is never written by two at once


def read_index(library_dir: Path) -> list[dict]:
    index_path = library_dir / INDEX_NAME
    if not index_path.is_file():
        return []
    with open(index_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_index(library_dir: Path, rows: list[dict]) -> None:
    with open(library_dir / INDEX_NAME, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def original_names(library_dir: Path) -> dict[str, str]:
    """Library file name -> the name the map had when it was added."""
    return {row["library_name"]: row["original_name"] for row in read_index(library_dir)}


def _candidates(sources: list[Path], library_dir: Path) -> tuple[list[Path], list[Path], int]:
    """Map files found under sources, paths that do not exist, and a count of non-map files."""
    library = library_dir.resolve()
    found, missing, not_maps = [], [], 0
    for source in sources:
        source = source.expanduser()
        if source.is_file():
            files = [source]
        elif source.is_dir():
            files = list(iter_files(source))
        else:
            missing.append(source)
            continue
        for path in files:
            if library in path.resolve().parents:
                continue  # already inside the library
            if path.suffix.lower() in MAP_EXTENSIONS:
                found.append(path)
            else:
                not_maps += 1
    return found, missing, not_maps


def _present(library_dir: Path, index: list[dict]) -> tuple[list[dict], set[str]]:
    """Index rows whose copy is still in the folder, and their fingerprints."""
    kept = [row for row in index if (library_dir / row["library_name"]).is_file()]
    return kept, {row["file_id"] for row in kept}


def _store(source: Path, original_name: str, origin: str, library_dir: Path, index: list[dict]) -> dict:
    """Copy one map into the library and return its new index row."""
    file_id = hash_file(source)
    name = Path(original_name).name
    library_name = f"{Path(name).stem[:150]}__{file_id[:10]}{Path(name).suffix.lower()}"
    shutil.copy2(source, library_dir / library_name)  # copy2 keeps the file's own dates
    row = {
        "file_id": file_id,
        "library_name": library_name,
        "original_name": name,
        "original_path": origin,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    index.append(row)
    return row


def add_maps(sources: list[Path], library_dir: Path) -> dict:
    """Copy every map under sources into the library. Maps already there are skipped."""
    library_dir.mkdir(parents=True, exist_ok=True)
    found, missing, not_maps = _candidates(sources, library_dir)
    added, already = [], 0
    with _lock:
        index, present = _present(library_dir, read_index(library_dir))
        for path in found:
            if hash_file(path) in present:
                already += 1
                continue
            row = _store(path, path.name, str(path.resolve()), library_dir, index)
            present.add(row["file_id"])
            added.append(path.name)
        _write_index(library_dir, index)
    return {"added": added, "already_in_library": already, "not_maps": not_maps, "missing": missing}


def add_file(source: Path, original_name: str, origin: str, library_dir: Path) -> str:
    """Add one file that arrived under another name (an upload from the Add maps screen).

    `origin` is recorded as where it came from. Returns "added", "already" or "not_map".
    """
    name = Path(original_name).name
    if Path(name).suffix.lower() not in MAP_EXTENSIONS or name.startswith("."):
        return "not_map"
    library_dir.mkdir(parents=True, exist_ok=True)
    with _lock:
        index, present = _present(library_dir, read_index(library_dir))
        if hash_file(source) in present:
            return "already"
        _store(source, name, origin, library_dir, index)
        _write_index(library_dir, index)
    return "added"
