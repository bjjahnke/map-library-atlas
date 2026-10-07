# Map Library Atlas

Geospatial index of my local map collection (PDFs and images). Shows each map's bounding-box footprint on a global base map.

**Read first:** `docs/HOW_IT_WORKS.md` (how it works today) and `docs/DEVELOPER.md` (technical reference and known limitations). `PROJECT_SCOPE.md` is the plan, updated to match what was built.

## How to work with me
- **One small step at a time.** Describe the step in plain words, wait for my go-ahead, build only that, then show me the result and a simple way to check it myself. Do not build ahead.
- **Plain language.** Avoid jargon, or explain it in a few words. Keep messages short. Make routine technical choices yourself; bring me the choices that affect what I see or do.
- **Keep the docs current.** When behaviour changes, update `docs/HOW_IT_WORKS.md`, `docs/DEVELOPER.md`, `docs/QUICKSTART.md` and `PROJECT_SCOPE.md` in the same step.
- Add tests for each change and tell me how to run it.

## Project rules
- Maps enter through `atlas add`, which copies them into one flat `library/` folder (named `<original name>__<hash start>`, with `library/index.csv`). The pipeline reads only the library; my own folder structure must not matter.
- Medallion layers: bronze (raw inventory), silver (resolved bbox, WGS84), gold (display-ready GeoJSON). Schemas are in `docs/DEVELOPER.md`.
- Manual inputs live in `config/regions.csv` and `config/map_manifest.csv`. **I assign every box by hand.** Bbox resolution order: manual box, then region default, else `needs_georef`. Embedded georeferencing is recorded but only used if `use_embedded_location: true` in `config.yaml` (off by default).
- `config/` is hand-edited; the pipeline may add blank rows or columns to the manifest but must never change what I typed. `data/` is rebuilt by the pipeline.
- Pipeline must be idempotent (skip unchanged files).
- **Never modify or move source map files.** Copying them into `library/` is the only thing done with them.
- Flag problem maps with a `status` instead of dropping them.
- Ask before changing schemas or the stack.
- Never commit map files, personal paths, `config.yaml`, `config/map_manifest.csv`, `library/`, or `data/`.

## Current state
`main` (tagged `v0.1`) is the working MVP on 26 test maps. Work in progress is on the branch `simpler-map-intake`; do not build on `main`.

Direction: this is meant to grow into a shared map-finder platform stocked with my maps. Planned next, one step at a time: (1) several place labels per map with a ready-made list of countries and US states, plus publisher and source link; (2) add-and-label screens in the browser with drag-and-drop, replacing hand-editing of the manifest; (3) load the rest of my collection. Do not ingest the full collection yet.
