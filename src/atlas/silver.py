"""Silver layer: one row per map with its bounding box in WGS84 (EPSG:4326).

Bbox resolution order: manual box in the manifest, then (only if switched on in
config) the location stored inside the file, then the region default, else `needs_georef`.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import duckdb
import numpy as np
from rasterio.crs import CRS
from rasterio.warp import transform, transform_bounds

from atlas.manifest import is_flagged

DENSIFY_POINTS = 21

COLUMNS = (
    "map_id",
    "title",
    "format",
    "width_px",
    "height_px",
    "is_georeferenced",
    "georef_method",
    "region_key",
    "bbox_source",
    "bbox_precision",
    "source_crs",
    "min_lon",
    "min_lat",
    "max_lon",
    "max_lat",
    "status",
    "status_detail",
    "duplicate_of",
)

_CREATE = """
CREATE SCHEMA IF NOT EXISTS silver;
CREATE OR REPLACE TABLE silver.maps (
    map_id           VARCHAR,
    title            VARCHAR,
    format           VARCHAR,
    width_px         INTEGER,
    height_px        INTEGER,
    is_georeferenced BOOLEAN,
    georef_method    VARCHAR,
    region_key       VARCHAR,
    bbox_source      VARCHAR,
    bbox_precision   VARCHAR,
    source_crs       VARCHAR,
    min_lon          DOUBLE,
    min_lat          DOUBLE,
    max_lon          DOUBLE,
    max_lat          DOUBLE,
    status           VARCHAR,
    status_detail    VARCHAR,
    duplicate_of     VARCHAR
);
"""


def clean_title(file_name: str) -> str:
    return re.sub(r"[\s_-]+", " ", Path(file_name).stem).strip()


def _describe_crs(crs: CRS) -> str:
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.to_wkt()


def _densify_ring(xs, ys):
    """Add points along each edge of a closed ring so curved edges survive reprojection."""
    out_x, out_y = [], []
    for i in range(len(xs)):
        j = (i + 1) % len(xs)
        out_x.extend(np.linspace(xs[i], xs[j], DENSIFY_POINTS, endpoint=False))
        out_y.extend(np.linspace(ys[i], ys[j], DENSIFY_POINTS, endpoint=False))
    return out_x, out_y


def bbox_from_pdf_viewport(viewport: dict) -> tuple[tuple[float, float, float, float], str]:
    """Bounding box (min_lon, min_lat, max_lon, max_lat) in WGS84 for one geospatial viewport."""
    gpts = viewport["gpts"]
    lats, lons = gpts[0::2], gpts[1::2]
    if len(lats) < 3 or len(lats) != len(lons):
        raise ValueError("viewport has no usable corner points")
    if viewport.get("epsg"):
        crs = CRS.from_epsg(viewport["epsg"])
    elif viewport.get("wkt"):
        crs = CRS.from_wkt(viewport["wkt"])
    else:
        raise ValueError("viewport has no coordinate system")

    # Corner points are lat/lon on the map's own datum. The map frame is straight-edged in
    # the map's projection, so densify there before converting to WGS84.
    if crs.is_projected:
        xs, ys = transform(crs.geodetic_crs, crs, lons, lats)
        xs, ys = _densify_ring(xs, ys)
        out_lons, out_lats = transform(crs, "EPSG:4326", xs, ys)
    else:
        xs, ys = _densify_ring(lons, lats)
        out_lons, out_lats = transform(crs, "EPSG:4326", xs, ys)
    return (min(out_lons), min(out_lats), max(out_lons), max(out_lats)), _describe_crs(crs)


def _main_viewport(viewports: list[dict]) -> dict:
    """The largest viewport on the first georeferenced page (the main map, not an inset)."""
    first_page = min(v["page"] for v in viewports)

    def page_area(v):
        x0, y0, x1, y1 = v["bbox"]
        return abs(x1 - x0) * abs(y1 - y0)

    return max((v for v in viewports if v["page"] == first_page), key=page_area)


def _validate(bbox) -> str | None:
    min_lon, min_lat, max_lon, max_lat = bbox
    if not all(np.isfinite(bbox)):
        return "bounding box is not finite"
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        return "latitude outside [-90, 90]"
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        return "longitude outside [-180, 180]"
    if not (min_lon < max_lon and min_lat < max_lat):
        return "bounding box has no area (min is not less than max)"
    if max_lon - min_lon > 180:
        return "bounding box may cross the antimeridian (wider than 180 degrees)"
    return None


BOX_FIELDS = ("min_lon", "min_lat", "max_lon", "max_lat")


def _embedded_bbox(meta: dict):
    """(bbox, source_crs, note) from location stored inside the file, or None if there is none."""
    if meta.get("geo_viewports"):
        viewports = meta["geo_viewports"]
        bbox, source_crs = bbox_from_pdf_viewport(_main_viewport(viewports))
        note = None
        if len(viewports) > 1:
            note = f"{len(viewports)} georeferenced areas in the file; used the largest on the first page"
        return bbox, source_crs, note
    if meta.get("crs") and meta.get("has_transform"):
        crs = CRS.from_wkt(meta["crs"])
        bbox = transform_bounds(crs, "EPSG:4326", *meta["bounds"], densify_pts=DENSIFY_POINTS)
        return bbox, _describe_crs(crs), None
    return None


def _box_from_fields(fields: dict, what: str):
    """A box typed by hand: None if all four cells are blank, an error if only partly filled."""
    values = [fields.get(name, "") for name in BOX_FIELDS]
    if not any(values):
        return None
    if not all(values):
        raise ValueError(f"{what} is incomplete: fill in all four of {', '.join(BOX_FIELDS)}")
    try:
        return tuple(float(v) for v in values)
    except ValueError:
        raise ValueError(f"{what} has a value that is not a number: {values}") from None


def resolve_map(
    file_id: str,
    file_name: str,
    extension: str,
    raw_metadata: dict | None,
    manual: dict | None = None,
    regions: dict[str, dict] | None = None,
    use_embedded: bool = False,
) -> dict:
    """Turn one bronze row (plus its manifest row, if any) into one silver row."""
    meta = raw_metadata or {}
    manual = manual or {}
    regions = regions or {}
    base_format = {"jpeg": "jpg", "tif": "tiff"}.get(extension, extension)
    region_key = manual.get("region_key", "").lower() or None
    # "come back to this one": stays visible in status_detail whether or not it has a box yet
    revisit = "marked to come back to" if is_flagged(manual) else None
    if revisit and manual.get("notes"):
        revisit += f": {manual['notes']}"
    row = dict.fromkeys(COLUMNS)
    row |= {
        "map_id": file_id,
        "title": manual.get("title") or clean_title(file_name),
        "format": base_format,
        "width_px": meta.get("width"),
        "height_px": meta.get("height"),
        "is_georeferenced": False,
        "georef_method": "none",
        "region_key": region_key,
        "bbox_source": "none",
        "status": "needs_georef",
        "status_detail": revisit or "no box or region entered in the manifest",
    }
    if "error" in meta:
        return row | {"status": "error", "status_detail": meta["error"]}

    # What the file itself says. Recorded as a fact; only used for the box if switched on.
    embedded = embedded_error = None
    try:
        embedded = _embedded_bbox(meta)
    except Exception as exc:
        embedded_error = f"could not read embedded location: {exc}"
    if embedded or embedded_error or meta.get("geo_viewports"):
        row |= {"is_georeferenced": True, "georef_method": "embedded"}
        row["format"] = {"pdf": "geopdf", "tiff": "geotiff"}.get(base_format, base_format)
        if embedded:
            row["source_crs"] = embedded[1]

    try:
        manual_box = _box_from_fields(manual, "the box in the manifest")
        if manual_box:
            bbox, source, precision, note = manual_box, "manual_override", "exact", None
        elif use_embedded and embedded_error:
            raise ValueError(embedded_error)
        elif use_embedded and embedded:
            bbox, source, precision, note = embedded[0], "embedded", "exact", embedded[2]
        elif region_key:
            if region_key not in regions:
                raise ValueError(f"region '{region_key}' is not in regions.csv")
            bbox = _box_from_fields(regions[region_key], f"region '{region_key}' in regions.csv")
            if bbox is None:
                raise ValueError(f"region '{region_key}' has no box in regions.csv")
            source, precision, note = "region_default", "approximate", None
        else:
            return row
    except ValueError as exc:
        return row | {"status": "error", "status_detail": str(exc)}

    row |= {
        "bbox_source": source,
        "bbox_precision": precision,
        "min_lon": round(bbox[0], 6),
        "min_lat": round(bbox[1], 6),
        "max_lon": round(bbox[2], 6),
        "max_lat": round(bbox[3], 6),
    }
    problem = _validate(bbox)
    if problem:
        return row | {"status": "error", "status_detail": problem}
    return row | {"status": "ok", "status_detail": "; ".join(filter(None, (revisit, note))) or None}


def build_silver(
    db_path: Path,
    manifest: dict[str, dict] | None = None,
    regions: dict[str, dict] | None = None,
    use_embedded: bool = False,
) -> dict:
    """Rebuild silver.maps from bronze and the manual inputs. Always recomputed in full."""
    manifest = manifest or {}
    with duckdb.connect(str(db_path)) as con:
        bronze = con.execute(
            "SELECT file_id, file_name, extension, raw_metadata FROM bronze.file_inventory "
            "ORDER BY file_name, file_path"
        ).fetchall()
        rows = [
            resolve_map(
                file_id,
                file_name,
                extension,
                json.loads(raw) if raw else None,
                manifest.get(file_name),
                regions,
                use_embedded,
            )
            for file_id, file_name, extension, raw in bronze
        ]
        con.execute(_CREATE)
        if rows:
            con.executemany(
                f"INSERT INTO silver.maps VALUES ({', '.join('?' * len(COLUMNS))})",
                [[row[c] for c in COLUMNS] for row in rows],
            )
    counts = {"total": len(rows), "ok": 0, "needs_georef": 0, "error": 0, "revisit": 0}
    for row in rows:
        counts[row["status"]] += 1
        counts["revisit"] += (row["status_detail"] or "").startswith("marked to come back to")
    return counts


def export_csv(db_path: Path, csv_path: Path) -> int:
    """Write silver as a spreadsheet-friendly CSV, with the file name added for readability."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            f"SELECT b.file_name, {', '.join('s.' + c for c in COLUMNS)} "
            "FROM silver.maps s JOIN (SELECT file_id, min(file_name) AS file_name "
            "FROM bronze.file_inventory GROUP BY file_id) b ON b.file_id = s.map_id "
            "ORDER BY b.file_name"
        ).fetchall()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(("file_name",) + COLUMNS)
        writer.writerows(rows)
    return len(rows)
