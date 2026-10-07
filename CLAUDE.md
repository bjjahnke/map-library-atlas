# Map Library Atlas

Geospatial index of my local map collection (PDFs and images). Shows each map's bounding-box footprint on a global base map.

**Read first:** `docs/HOW_IT_WORKS.md` (how it works today) and `docs/DEVELOPER.md` (technical reference and known limitations). `PROJECT_SCOPE.md` is the plan, updated to match what was built.

## How to work with me
- **One small step at a time.** Describe the step in plain words, wait for my go-ahead, build only that, then show me the result and a simple way to check it myself. Do not build ahead.
- **Plain language.** Avoid jargon, or explain it in a few words. Keep messages short. Make routine technical choices yourself; bring me the choices that affect what I see or do.
- **Keep the docs current.** When behaviour changes, update `docs/HOW_IT_WORKS.md`, `docs/DEVELOPER.md`, `docs/QUICKSTART.md` and `PROJECT_SCOPE.md` in the same step.
- Add tests for each change and tell me how to run it.

## Project rules
- **Words:** a map's *places* are tags (where it is; for finding and filtering). Its *footprint* is the shape drawn on the globe, chosen separately (around its places / its own rectangle / none yet). Say "footprint", not "bounding box", in anything I read: rectangles are a stand-in until true map outlines are possible, which is a much later goal.
- Maps enter through `atlas add`, which copies them into one flat `library/` folder (named `<original name>__<hash start>`, with `library/index.csv`). The pipeline reads only the library; my own folder structure must not matter.
- Medallion layers: bronze (raw inventory), silver (resolved bbox, WGS84), gold (display-ready GeoJSON). Schemas are in `docs/DEVELOPER.md`.
- Manual inputs live in `config/regions.csv` and `config/map_manifest.csv`. **I assign every box by hand.** Bbox resolution order: manual box, then region default, else `needs_georef`. Embedded georeferencing is recorded but only used if `use_embedded_location: true` in `config.yaml` (off by default).
- Labels live in `config/map_manifest.csv`, keyed by `file_id`, and are edited through the Label maps screen (`atlas view`). The pipeline may add blank rows or columns and fill in `file_id`, but must never change a label by itself. `data/` is rebuilt by the pipeline.
- Pipeline must be idempotent (skip unchanged files).
- **Never modify or move source map files.** Copying them into `library/` is the only thing done with them.
- Flag problem maps with a `status` instead of dropping them.
- Ask before changing schemas or the stack.
- Never commit map files, personal paths, `config.yaml`, `config/map_manifest.csv`, `library/`, or `data/`.

## Current state
`main` (tagged `v0.1`) is the working MVP on 26 test maps. Work in progress is on the branch `simpler-map-intake`; do not build on `main`.

Direction: this is meant to grow into a shared map-finder platform stocked with my maps (about 200 US maps to start, a few per state). **Using the atlas must never need the terminal or hand-editing files; the terminal is for development only.**

Done on the branch: library folder and `atlas add`; `config/regions.csv` with all US states and territories; several places per map (`;`-separated in `region_key`, one box around all); `atlas view` is now a small local web app (stdlib only) with three tabs: Globe; Label maps (preview, tag places, choose footprint, rename, park, filter by place, save); Add maps (drag and drop files or folders into the library).

**New maps must arrive untagged.** I do not want places or footprints guessed from folder or file names; labelling is a manual QA step for now.

Planned next, one step at a time: (1) a double-click icon that opens the atlas; (2) bulk labelling (apply one place to several selected maps; no automatic suggestions); (4) test run on two or three state folders; (5) the rest of the US catalog. Later: publisher and source link per map, other countries. Do not ingest the full collection yet.
