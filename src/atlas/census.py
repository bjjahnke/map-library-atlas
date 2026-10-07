"""Phase 1 census: file counts by format and how many are georeferenced.

Strictly read-only. Only file headers are inspected; nothing is hashed or stored.
"""

from __future__ import annotations

import os
import warnings
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import rasterio
from pypdf import PdfReader
from rasterio.errors import NotGeoreferencedWarning

# extension -> base format (before georeferencing is known)
MAP_EXTENSIONS = {
    ".pdf": "pdf",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
}

WORLD_FILE_EXTENSIONS = {
    "tiff": (".tfw", ".tifw", ".tiffw", ".wld"),
    "jpg": (".jgw", ".jpgw", ".jpegw", ".wld"),
    "png": (".pgw", ".pngw", ".wld"),
}
_ALL_WORLD_FILE_EXTENSIONS = {e for exts in WORLD_FILE_EXTENSIONS.values() for e in exts}

FORMAT_ORDER = ("geopdf", "pdf", "geotiff", "tiff", "jpg", "png")


@dataclass
class FileRecord:
    path: str
    format: str
    georef_method: str = "none"  # embedded | worldfile | none
    crs: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    pages: int | None = None  # PDFs only
    geo_pages: int | None = None  # PDFs only
    status: str = "ok"  # ok | error
    status_detail: str | None = None

    @property
    def is_georeferenced(self) -> bool:
        return self.georef_method != "none"


def iter_files(folder: Path):
    """Yield every non-hidden file under folder, in a stable order."""
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if not name.startswith("."):
                yield Path(root) / name


def find_world_file(path: Path, base_format: str) -> Path | None:
    for ext in WORLD_FILE_EXTENSIONS.get(base_format, ()):
        for candidate in (path.with_suffix(ext), path.with_suffix(ext.upper())):
            if candidate.is_file():
                return candidate
    return None


def _inspect_raster(path: Path, base_format: str) -> FileRecord:
    record = FileRecord(path=str(path), format=base_format)
    world_file = find_world_file(path, base_format)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path) as src:
            record.width_px, record.height_px = src.width, src.height
            crs = src.crs
            has_transform = not src.transform.is_identity
            has_gcps = bool(src.gcps[0])
    if crs:
        record.crs = crs.to_string()

    if base_format == "tiff":
        # GDAL also applies a sidecar world file, so a bare transform only counts
        # as embedded when there is no sidecar to explain it.
        if crs or has_gcps or (has_transform and world_file is None):
            record.georef_method = "embedded"
            record.format = "geotiff"
        elif world_file:
            record.georef_method = "worldfile"
    elif world_file:
        record.georef_method = "worldfile"
    elif crs or has_transform or has_gcps:
        record.georef_method = "embedded"
    return record


def _page_is_geospatial(page) -> bool:
    # OGC best-practice (TerraGo) GeoPDF
    if "/LGIDict" in page:
        return True
    # ISO 32000 geospatial PDF: a viewport with a GEO measure dictionary
    for viewport in page.get("/VP", []) or []:
        measure = viewport.get_object().get("/Measure")
        if measure is not None and measure.get_object().get("/Subtype") == "/GEO":
            return True
    return False


def _inspect_pdf(path: Path) -> FileRecord:
    record = FileRecord(path=str(path), format="pdf")
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is password-protected")
    record.pages = len(reader.pages)
    record.geo_pages = sum(1 for page in reader.pages if _page_is_geospatial(page))
    if record.geo_pages:
        record.georef_method = "embedded"
        record.format = "geopdf"
    return record


def inspect_file(path: Path) -> FileRecord | None:
    """Classify one file. Returns None for files that are not a map format."""
    base_format = MAP_EXTENSIONS.get(path.suffix.lower())
    if base_format is None:
        return None
    try:
        if base_format == "pdf":
            return _inspect_pdf(path)
        return _inspect_raster(path, base_format)
    except Exception as exc:  # unreadable maps are flagged, never dropped
        return FileRecord(
            path=str(path),
            format=base_format,
            status="error",
            status_detail=f"{type(exc).__name__}: {exc}",
        )


def run_census(folder: Path) -> dict:
    if not folder.is_dir():
        raise NotADirectoryError(f"maps_folder does not exist or is not a folder: {folder}")

    records: list[FileRecord] = []
    ignored: Counter[str] = Counter()
    for path in iter_files(folder):
        record = inspect_file(path)
        if record is not None:
            records.append(record)
        elif path.suffix.lower() not in _ALL_WORLD_FILE_EXTENSIONS:
            ignored[path.suffix.lower() or "(no extension)"] += 1

    by_format: dict[str, dict] = {}
    for fmt in FORMAT_ORDER:
        rows = [r for r in records if r.format == fmt]
        if rows:
            by_format[fmt] = {
                "total": len(rows),
                "georeferenced": sum(r.is_georeferenced for r in rows),
                "embedded": sum(r.georef_method == "embedded" for r in rows),
                "worldfile": sum(r.georef_method == "worldfile" for r in rows),
                "errors": sum(r.status == "error" for r in rows),
            }

    return {
        "folder": str(folder),
        "total_maps": len(records),
        "georeferenced": sum(r.is_georeferenced for r in records),
        "not_georeferenced": sum(not r.is_georeferenced and r.status == "ok" for r in records),
        "errors": sum(r.status == "error" for r in records),
        "multi_page_pdfs": sum((r.pages or 0) > 1 for r in records),
        "by_format": by_format,
        "ignored_extensions": dict(sorted(ignored.items())),
        "files": [asdict(r) | {"is_georeferenced": r.is_georeferenced} for r in records],
    }


def format_report(census: dict, verbose: bool = False) -> str:
    total = census["total_maps"]
    lines = [f"Census of {census['folder']}", ""]
    header = f"{'format':<10}{'files':>7}{'georef':>8}{'embedded':>10}{'worldfile':>11}{'errors':>8}"
    lines += [header, "-" * len(header)]
    for fmt, c in census["by_format"].items():
        lines.append(
            f"{fmt:<10}{c['total']:>7}{c['georeferenced']:>8}{c['embedded']:>10}"
            f"{c['worldfile']:>11}{c['errors']:>8}"
        )
    lines.append("-" * len(header))
    lines.append(f"{'total':<10}{total:>7}{census['georeferenced']:>8}")
    lines.append("")

    share = f" ({census['georeferenced'] / total:.0%})" if total else ""
    lines.append(f"Georeferenced:      {census['georeferenced']}{share}")
    lines.append(f"Not georeferenced:  {census['not_georeferenced']}")
    lines.append(f"Unreadable (error): {census['errors']}")
    lines.append(f"Multi-page PDFs:    {census['multi_page_pdfs']}")
    if census["ignored_extensions"]:
        ignored = ", ".join(f"{ext} x{n}" for ext, n in census["ignored_extensions"].items())
        lines.append(f"Ignored non-map files: {ignored}")

    errors = [f for f in census["files"] if f["status"] == "error"]
    if errors:
        lines += ["", "Errors:"]
        lines += [f"  {f['path']}: {f['status_detail']}" for f in errors]

    if verbose:
        lines += ["", "Files:"]
        for f in census["files"]:
            extra = f", {f['pages']} pages" if (f["pages"] or 0) > 1 else ""
            lines.append(f"  [{f['format']}, {f['georef_method']}{extra}] {f['path']}")
    return "\n".join(lines)
