"""Command line entry point: `atlas census`, `atlas add`, `atlas run`, `atlas view`."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import sys
import webbrowser
from pathlib import Path

from atlas import gold, library, silver
from atlas.bronze import build_inventory, export_csv, read_inventory
from atlas.census import format_report, run_census
from atlas.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    data_dir,
    library_dir,
    load_config,
    manifest_csv,
    maps_folder,
    regions_csv,
)
from atlas.manifest import ensure_manifest, load_manifest, load_regions


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas", description="Map Library Atlas pipeline")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    census = sub.add_parser("census", help="count map files by format and georeferencing")
    census.add_argument("--folder", type=Path, help="folder to scan (overrides maps_folder in config)")
    census.add_argument("--json", action="store_true", help="print the full census as JSON")
    census.add_argument("-v", "--verbose", action="store_true", help="list every file")

    add = sub.add_parser("add", help="copy maps into the library (originals are not touched)")
    add.add_argument("paths", type=Path, nargs="+", help="map files, or folders of maps")

    sub.add_parser("run", help="rebuild the list, boxes and viewer files from the library")

    view = sub.add_parser("view", help="open the globe viewer in your browser")
    view.add_argument("--port", type=int, default=8000)
    view.add_argument("--no-browser", action="store_true", help="start the viewer without opening a browser")
    return parser


def _serve_viewer(port: int, open_browser: bool) -> int:
    """Serve the project folder to this computer only, so the viewer can read the gold file."""
    if not Path("viewer/index.html").is_file():
        print("error: run this from the project folder (viewer/index.html not found).", file=sys.stderr)
        return 2
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=".")
    url = f"http://127.0.0.1:{port}/viewer/"
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        print(f"error: could not start on port {port} ({exc}). Try --port 8001.", file=sys.stderr)
        return 2
    with server:
        print(f"Viewer running at {url}")
        print("Press Ctrl+C here to stop it.")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nViewer stopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "census":
        try:
            folder = args.folder or maps_folder(load_config(args.config))
            census = run_census(folder.expanduser())
        except (ConfigError, NotADirectoryError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(census, indent=2) if args.json else format_report(census, args.verbose))
        return 0

    if args.command == "view":
        return _serve_viewer(args.port, not args.no_browser)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    maps_library = library_dir(config)

    if args.command == "add":
        result = library.add_maps(args.paths, maps_library)
        print(f"Added to the library:   {len(result['added'])}")
        print(f"Already in the library: {result['already_in_library']}")
        if result["not_maps"]:
            print(f"Skipped (not map files): {result['not_maps']}")
        for path in result["missing"]:
            print(f"Not found: {path}")
        if result["added"]:
            print("\nNext: run `atlas run` to update the atlas.")
        return 2 if result["missing"] else 0

    maps_library.mkdir(parents=True, exist_ok=True)
    db_path = data_dir(config) / "atlas.duckdb"
    csv_path = data_dir(config) / "bronze" / "file_inventory.csv"
    counts = build_inventory(maps_library, db_path, library.original_names(maps_library))
    export_csv(db_path, csv_path)
    names = [row["file_name"] for row in read_inventory(db_path)]
    added = ensure_manifest(manifest_csv(config), names)

    print(f"Maps in the library: {counts['total']}")
    print(f"  new: {counts['new']}, changed: {counts['changed']}, unchanged: {counts['unchanged']}")
    if counts["removed"]:
        print(f"  no longer in the library, so dropped from the list: {counts['removed']}")
    if not counts["total"]:
        print("  The library is empty. Add maps with: atlas add <file or folder>")
    print(f"List to look at:     {csv_path}")
    print(f"File for your notes: {manifest_csv(config)} ({added} blank rows added)")

    silver_csv = data_dir(config) / "silver" / "maps.csv"
    # bronze keeps a copy of the hand-edited files exactly as they were for this run
    copies = data_dir(config) / "bronze" / "manual_inputs"
    copies.mkdir(parents=True, exist_ok=True)
    for source in (manifest_csv(config), regions_csv(config)):
        if source.is_file():
            shutil.copyfile(source, copies / source.name)

    located = silver.build_silver(
        db_path,
        load_manifest(manifest_csv(config)),
        load_regions(regions_csv(config)),
        use_embedded=bool(config.get("use_embedded_location", False)),
    )
    silver.export_csv(db_path, silver_csv)
    print()
    print(f"Maps with a box:        {located['ok']}")
    print(f"Maps needing a location: {located['needs_georef']}")
    print(f"Maps with a problem:     {located['error']}")
    print(f"Marked to come back to:  {located['revisit']}")
    print(f"Boxes to look at:    {silver_csv}")

    geojson = data_dir(config) / "gold" / "map_library.geojson"
    needs_review = data_dir(config) / "gold" / "needs_review.csv"
    finished = gold.build_gold(db_path, geojson, needs_review)
    print()
    print(f"Map file for the viewer: {geojson} ({finished['located']} maps)")
    print(f"To-do list:              {needs_review} ({finished['needs_review']} maps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
