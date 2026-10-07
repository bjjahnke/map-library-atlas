"""Command line entry point: `atlas census`, `atlas add`, `atlas run`, `atlas view`."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from atlas import library, pipeline, server
from atlas.census import format_report, run_census
from atlas.config import DEFAULT_CONFIG_PATH, ConfigError, library_dir, load_config, manifest_csv, maps_folder


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

    view = sub.add_parser("view", help="open the atlas (globe and label screen) in your browser")
    view.add_argument("--port", type=int, default=8000)
    view.add_argument("--no-browser", action="store_true", help="start the atlas without opening a browser")
    return parser


def _serve_viewer(config: dict, port: int, open_browser: bool) -> int:
    """Run the atlas app (globe and label screen) for this computer only."""
    url = f"http://127.0.0.1:{port}/viewer/"
    try:
        app = server.make_server(config, port)
    except OSError as exc:
        print(f"error: could not start on port {port} ({exc}). Try --port 8001.", file=sys.stderr)
        return 2
    with app:
        print(f"Atlas running at {url}")
        print("Press Ctrl+C here to stop it.")
        if open_browser:
            webbrowser.open(url)
        try:
            app.serve_forever()
        except KeyboardInterrupt:
            print("\nAtlas stopped.")
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

    if args.command == "view":
        return _serve_viewer(config, args.port, not args.no_browser)

    summary = pipeline.run(config)
    where = pipeline.paths(config)
    counts, located, finished = summary["inventory"], summary["located"], summary["gold"]

    print(f"Maps in the library: {counts['total']}")
    print(f"  new: {counts['new']}, changed: {counts['changed']}, unchanged: {counts['unchanged']}")
    if counts["removed"]:
        print(f"  no longer in the library, so dropped from the list: {counts['removed']}")
    if not counts["total"]:
        print("  The library is empty. Add maps with: atlas add <file or folder>")
    print(f"List to look at:     {where['bronze_csv']}")
    print(f"Labels file:         {manifest_csv(config)} ({summary['manifest_rows_added']} blank rows added)")
    print()
    print(f"Maps with a box:        {located['ok']}")
    print(f"Maps needing a location: {located['needs_georef']}")
    print(f"Maps with a problem:     {located['error']}")
    print(f"Marked to come back to:  {located['revisit']}")
    print(f"Boxes to look at:    {where['silver_csv']}")
    print()
    print(f"Map file for the viewer: {where['geojson']} ({finished['located']} maps)")
    print(f"To-do list:              {where['needs_review']} ({finished['needs_review']} maps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
