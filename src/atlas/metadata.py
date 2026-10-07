"""Read the raw, as-found metadata stored inside a map file. Read-only.

This is what bronze keeps in `raw_metadata`. GDAL's PDF reader is not available in the
bundled build, so PDFs are read with pypdf and rasters with rasterio.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import rasterio
from pypdf import PdfReader
from rasterio.errors import NotGeoreferencedWarning


def _floats(values) -> list[float]:
    return [float(v) for v in values or []]


def _pdf_metadata(path: Path) -> dict:
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is password-protected")

    viewports = []
    has_lgidict = False
    for page_number, page in enumerate(reader.pages):
        has_lgidict = has_lgidict or "/LGIDict" in page
        for viewport in page.get("/VP") or []:
            viewport = viewport.get_object()
            measure = viewport.get("/Measure")
            if measure is None or measure.get_object().get("/Subtype") != "/GEO":
                continue
            measure = measure.get_object()
            gcs = measure.get("/GCS")
            gcs = gcs.get_object() if gcs is not None else {}
            viewports.append(
                {
                    "page": page_number,
                    "bbox": _floats(viewport.get("/BBox")),  # position on the page, in points
                    "gpts": _floats(measure.get("/GPTS")),  # lat, lon pairs
                    "epsg": int(gcs["/EPSG"]) if "/EPSG" in gcs else None,
                    "wkt": str(gcs["/WKT"]) if "/WKT" in gcs else None,
                }
            )
    title = reader.metadata.title if reader.metadata else None
    return {
        "reader": "pypdf",
        "pages": len(reader.pages),
        "title": title,
        "geo_viewports": viewports,
        "has_lgidict": has_lgidict,
    }


def _raster_metadata(path: Path) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path) as src:
            return {
                "reader": "rasterio",
                "driver": src.driver,
                "width": src.width,
                "height": src.height,
                "crs": src.crs.to_wkt() if src.crs else None,
                "has_transform": not src.transform.is_identity,
                "bounds": list(src.bounds),
            }


def read_raw_metadata(path: Path) -> dict:
    """Never raises: an unreadable file comes back as {"error": ...} so it can be flagged."""
    try:
        if path.suffix.lower() == ".pdf":
            return _pdf_metadata(path)
        return _raster_metadata(path)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
