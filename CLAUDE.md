# Map Library Atlas

Geospatial index of my local map collection (PDFs and images). Shows each map's bounding-box footprint on a global base map.

**Read first:** `docs/HOW_IT_WORKS.md` (how it works today) and `docs/DEVELOPER.md` (technical reference and known limitations). `PROJECT_SCOPE.md` is the plan, updated to match what was built.

## How to work with me
- **One small step at a time.** Describe the step in plain words, wait for my go-ahead, build only that, then show me the result and a simple way to check it myself. Do not build ahead.
- **Plain language.** Avoid jargon, or explain it in a few words. Keep messages short. Make routine technical choices yourself; bring me the choices that affect what I see or do.
- **Keep the docs current.** When behaviour changes, update `docs/HOW_IT_WORKS.md`, `docs/DEVELOPER.md`, `docs/QUICKSTART.md` and `PROJECT_SCOPE.md` in the same step.
- Add tests for each change and tell me how to run it.

## Project rules
- Medallion layers: bronze (raw inventory), silver (resolved bbox, WGS84), gold (display-ready GeoJSON). Schemas are in `docs/DEVELOPER.md`.
- Manual inputs live in `config/regions.csv` and `config/map_manifest.csv`. **I assign every box by hand.** Bbox resolution order: manual box, then region default, else `needs_georef`. Embedded georeferencing is recorded but only used if `use_embedded_location: true` in `config.yaml` (off by default).
- `config/` is hand-edited; the pipeline may add blank rows or columns to the manifest but must never change what I typed. `data/` is rebuilt by the pipeline.
- Pipeline must be idempotent (skip unchanged files).
- **Never modify or move source map files.**
- Flag problem maps with a `status` instead of dropping them.
- Ask before changing schemas or the stack.
- Never commit map files, personal paths, `config.yaml`, `config/map_manifest.csv`, or `data/`.

## Current state
MVP works end to end on a 26-map test folder: `atlas census`, `atlas run`, `atlas view`. Do not ingest the full library yet.
