"""Gold layer: what the viewer reads.

`gold.map_library` holds the located maps (status ok); `gold.needs_review` holds the rest.
Kept deliberately small: a title, where the file lives, and the box.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb

_BUILD = """
CREATE SCHEMA IF NOT EXISTS gold;

CREATE OR REPLACE TABLE gold.map_library AS
SELECT DISTINCT s.map_id, s.title, b.file_path, s.min_lon, s.min_lat, s.max_lon, s.max_lat
FROM silver.maps s JOIN bronze.file_inventory b ON b.file_id = s.map_id
WHERE s.status = 'ok'
ORDER BY s.title, b.file_path;

CREATE OR REPLACE TABLE gold.needs_review AS
SELECT DISTINCT s.map_id, s.title, b.file_path, s.status, s.status_detail
FROM silver.maps s JOIN bronze.file_inventory b ON b.file_id = s.map_id
WHERE s.status <> 'ok'
ORDER BY s.title, b.file_path;
"""

NEEDS_REVIEW_COLUMNS = ("title", "file_path", "status", "status_detail")


def _feature(title, file_path, min_lon, min_lat, max_lon, max_lat) -> dict:
    ring = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]
    return {
        "type": "Feature",
        "properties": {"title": title, "file_path": file_path},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def build_gold(db_path: Path, geojson_path: Path, needs_review_path: Path) -> dict:
    """Rebuild both gold tables from silver and write the two output files."""
    with duckdb.connect(str(db_path)) as con:
        con.execute(_BUILD)
        located = con.execute(
            "SELECT title, file_path, min_lon, min_lat, max_lon, max_lat FROM gold.map_library "
            "ORDER BY title, file_path"
        ).fetchall()
        review = con.execute(
            f"SELECT {', '.join(NEEDS_REVIEW_COLUMNS)} FROM gold.needs_review ORDER BY title, file_path"
        ).fetchall()

    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", "features": [_feature(*row) for row in located]}
    geojson_path.write_text(json.dumps(collection, indent=2) + "\n")

    needs_review_path.parent.mkdir(parents=True, exist_ok=True)
    with open(needs_review_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(NEEDS_REVIEW_COLUMNS)
        writer.writerows(review)

    return {"located": len(located), "needs_review": len(review)}
