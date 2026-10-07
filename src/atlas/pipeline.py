"""Run the whole pipeline once: library -> bronze -> silver -> gold."""

from __future__ import annotations

import shutil
from pathlib import Path

from atlas import bronze, gold, library, silver
from atlas.config import data_dir, library_dir, manifest_csv, regions_csv
from atlas.manifest import load_manifest, load_regions, sync_manifest


def paths(config: dict) -> dict[str, Path]:
    data = data_dir(config)
    return {
        "db": data / "atlas.duckdb",
        "bronze_csv": data / "bronze" / "file_inventory.csv",
        "manual_copies": data / "bronze" / "manual_inputs",
        "silver_csv": data / "silver" / "maps.csv",
        "geojson": data / "gold" / "map_library.geojson",
        "needs_review": data / "gold" / "needs_review.csv",
        "thumbnails": data / "thumbnails",
    }


def run(config: dict) -> dict:
    """Rebuild everything in data/ from the library and the manual inputs."""
    where = paths(config)
    maps_library = library_dir(config)
    maps_library.mkdir(parents=True, exist_ok=True)

    inventory = bronze.build_inventory(maps_library, where["db"], library.original_names(maps_library))
    bronze.export_csv(where["db"], where["bronze_csv"])
    maps = [(row["file_id"], row["file_name"]) for row in bronze.read_inventory(where["db"])]
    rows_added = sync_manifest(manifest_csv(config), maps)

    # bronze keeps a copy of the hand-edited files exactly as they were for this run
    where["manual_copies"].mkdir(parents=True, exist_ok=True)
    for source in (manifest_csv(config), regions_csv(config)):
        if source.is_file():
            shutil.copyfile(source, where["manual_copies"] / source.name)

    located = silver.build_silver(
        where["db"],
        load_manifest(manifest_csv(config)),
        load_regions(regions_csv(config)),
        use_embedded=bool(config.get("use_embedded_location", False)),
    )
    silver.export_csv(where["db"], where["silver_csv"])
    finished = gold.build_gold(where["db"], where["geojson"], where["needs_review"])
    return {"inventory": inventory, "manifest_rows_added": rows_added, "located": located, "gold": finished}
