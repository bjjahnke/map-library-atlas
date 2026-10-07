# Map Library Atlas: Project Scope

> A geospatial index of my local map collection. Instead of browsing folders, I open a global base map and see the **footprint of every map I own**, so I know where I have coverage.

> **Status (7 October 2026):** the MVP works end to end on a 26-map test folder. This
> document has been updated to match what was built. Guides: `docs/QUICKSTART.md` (adding
> maps), `docs/HOW_IT_WORKS.md` (plain-language walkthrough), `docs/DEVELOPER.md`
> (technical reference, including every change from the original plan).

---

## 1. Problem

- Maps live in folders as **PDFs and images** in mixed formats.
- A folder view can't answer: *What do I have? Where? Where are the gaps?*
- No geospatial view of the collection exists.

## 2. Goal

Show the **bounding-box footprint of each map** on a global base map (Google Earth-style), with click-through to the source file.

**This is the foundation layer.** Later features build on it.

## 3. MVP Scope

### In scope
- Copy PDF and image maps from anywhere on disk into one flat library folder (`atlas add`), and scan that
- Record metadata and georeferencing where it exists (recorded; not used for the box by default)
- Compute one **bounding box** per map (min/max lat/lon, WGS84)
- Store results in a Medallion-style pipeline (bronze, silver, gold)
- Web viewer: base map + bbox rectangles + click popup listing every map under the clicked point (title, file path)
- Flag maps that **can't** be located so they're tracked, not lost

### Out of scope (later)
- True map outlines (polygons, neatlines, rotated footprints)
- Rendering the actual map imagery on the base layer
- Auto-georeferencing of non-georeferenced maps
- Search/filter UI, tagging, coverage-gap analysis
- Cloud hosting, multi-user

---

## 4. Critical Risk: Where Do Coordinates Come From?

The pipeline only works if each map has a location. By format:

| Format | Georeferencing? | Approach |
|---|---|---|
| **GeoPDF** | Embedded | Detected and read with pypdf |
| **GeoTIFF** | Embedded | Detected and read with rasterio |
| **JPG/PNG + world file** (`.jgw`, `.pgw`, `.wld`) | Sidecar file | Detected in the census; not used (no CRS) |
| **Plain PDF / JPG / PNG** | **None** | Manual georeferencing, or fallback below |

**DECIDED for MVP:** bounding boxes are **entered manually**, with **region defaults** as a fallback (see Section 5.5).
- Non-georeferenced maps get a bbox from a manual override, or from their assigned region's default box.
- Anything with neither is flagged `needs_georef`.
- **Decided during the build:** every box is assigned by hand. Embedded georeferencing is read and recorded, but only used for the box when `use_embedded_location: true` is set in `config.yaml` (off by default). In the test folder the embedded boxes described the page's map frame, not the area of interest, and one PDF held six separate georeferenced areas.
- **Later:** QGIS georeferencer, or OCR/place-name heuristics.

> First task of the build: **run a census** of the folder (how many files per format, how many have embedded georeferencing). This tells you how big the problem actually is.
>
> **Census result for the test folder:** 26 maps: 16 GeoPDFs, 6 plain PDFs, 3 JPGs, 1 PNG. Three PDFs have two pages. None unreadable.

---

## 5. Pipeline Architecture (Medallion)

```
Maps anywhere ──► LIBRARY ──► BRONZE ──► SILVER ──► GOLD ──► Viewer
 (originals,      (flat folder  (inventory)  (cleaned,   (display-
  untouched)       of copies)                standard)    ready)
```

### Bronze: raw, as-found
**Purpose:** record what is in the library, untouched. Re-runnable. Mirrors the library: a map deleted from the library is dropped from the inventory.

Table `bronze.file_inventory`

| Column | Notes |
|---|---|
| `file_id` | SHA-256 of file contents (also detects duplicates). Not unique; `file_path` is the key |
| `file_path` | Absolute path of the library copy |
| `file_name`, `extension` | `file_name` is the map's original name |
| `size_bytes`, `modified_at` | |
| `ingested_at` | When the row was first recorded, or the file last changed |
| `raw_metadata` | Metadata read from inside the file, stored as-is (JSON): pypdf for PDFs, rasterio for rasters. Originally planned as `gdalinfo -json`; standalone GDAL is not installed |

Source files are **never modified or moved**; they are copied into `library/` as `<original name>__<hash start>.<ext>`, with `library/index.csv` recording where each came from.

### Silver: cleaned and standardized
**Purpose:** one trustworthy row per map, in a consistent coordinate system.

Table `silver.maps`

| Column | Notes |
|---|---|
| `map_id` | Stable ID (from `file_id`) |
| `title` | From the manifest `title`, else cleaned filename. PDF metadata titles proved unreliable and are not used |
| `format` | `geopdf`, `geotiff`, `tiff`, `jpg`, `png`, `pdf` |
| `width_px`, `height_px` | Raster size (blank for PDFs) |
| `is_georeferenced` | bool. Describes the file, not where the box came from |
| `georef_method` | `embedded` or `none` so far (`worldfile`, `manual_sidecar` reserved) |
| `region_key` | Region bucket from the manifest (e.g. `wisconsin`), nullable |
| `bbox_source` | `manual_override`, `region_default`, `embedded`, `none` |
| `bbox_precision` | `exact` (override/embedded) or `approximate` (region default) |
| `source_crs` | EPSG code or WKT as found |
| `min_lon`, `min_lat`, `max_lon`, `max_lat` | **Reprojected to EPSG:4326** |
| `status` | `ok`, `needs_georef`, `error` |
| `status_detail` | Error or reason text. Starts with `marked to come back to` for maps flagged `revisit` |
| `duplicate_of` | `map_id` of the original, if a hash duplicate (not populated yet) |

Cleansing rules:
- Reproject bbox to WGS84. **Densify edges before taking min/max** so projected maps don't produce bad boxes.
- Validate: lat in [-90, 90], lon in [-180, 180], min < max.
- Flag (don't silently fix) maps crossing the antimeridian (±180°).
- Dedupe by hash (not implemented yet).

### Gold: ready to display
**Purpose:** what the app reads. Only valid, located maps.

Table `gold.map_library`

| Column | Notes |
|---|---|
| `map_id`, `title`, `file_path` | |
| `min_lon`, `min_lat`, `max_lon`, `max_lat` | |

Kept deliberately minimal. `format`, `geometry` and `area_km2` from the original plan were dropped; the polygon is built from the four numbers at export time.

Export: `data/gold/map_library.geojson`. Each feature carries `title` and `file_path` only.

A second table, `gold.needs_review`, lists maps with `status != ok` for the review queue. Export: `data/gold/needs_review.csv`.

---

## 5.5 Manual Inputs (the "manual cleansing" step)

Manual data is **reference/seed data that you maintain by hand**. It is not a medallion layer, and it is never edited into bronze. It enters at **silver**, where it's joined to the raw inventory.

Two small files (CSV) in `config/`. The manifest is normally edited through the **Label maps** screen, which writes it; it can still be edited by hand:

**`regions.csv`**: reusable default boxes. Ships with all US states, DC, five territories, and two whole-country entries (58 rows)

| region_key | region_name | min_lon | min_lat | max_lon | max_lat |
|---|---|---|---|---|---|
| `wisconsin` | Wisconsin | -92.888114 | 42.491983 | -86.805415 | 47.080621 |

**`map_manifest.csv`**: one row per map. The pipeline adds a blank row for each new file and never edits what you typed

| Column | Notes |
|---|---|
| `file_id` | Which map this row describes (content hash). Filled in by the pipeline |
| `file_name` | The map's original name, for readability |
| `revisit` | `yes` to mark the map as one to come back to |
| `region_key` | Optional place, e.g. `wisconsin`. Several may be given, separated by `;`, and the box is drawn around all of them |
| `footprint` | How the shape on the globe is decided: `places`, `own`, or `none` (tagged only). Blank = own box if present, else places |
| `min_lon`, `min_lat`, `max_lon`, `max_lat` | The map's own rectangle, used when `footprint` is `own` |
| `title`, `notes` | Optional |

**Places are tags; the footprint is a separate choice.** "Footprint" means the shape drawn on the globe. It is a rectangle for now; true map outlines are a later goal (see Section 3, out of scope).

**Bbox resolution order (silver), for rows with a blank `footprint`:**
1. Manual override in the manifest → `exact`
2. Embedded georeferencing → `exact`. **Skipped unless `use_embedded_location: true`** (off by default)
3. Region default via `region_key` → `approximate`
4. Nothing → `needs_georef`

Mistakes in the manual files (a partly filled box, a non-number, an unknown region) set `status = error` with the reason, instead of being dropped or guessed at.

**Rules**
- Bronze keeps the raw files and a raw copy of both manual files as loaded. Silver applies the resolution logic. This keeps manual decisions auditable and the pipeline re-runnable.
- Silver records `bbox_source` / `bbox_precision`. Gold does **not** carry them yet, so the viewer draws all boxes alike. Styling region-default boxes differently (e.g. dashed outline) is a later option.
- Real file paths and the personal manifest stay out of git (add `config/map_manifest.csv` to `.gitignore`; commit a small `map_manifest.example.csv` and `regions.csv`).

---

## 6. Stack (as built)

| Layer | Choice | Why |
|---|---|---|
| Pipeline | **Python** | Best geospatial ecosystem |
| Raster reading | **rasterio** (bundles GDAL and PROJ) | Reads GeoTIFF and image headers |
| PDF reading | **pypdf** | Page count and GeoPDF viewports. rasterio's bundled GDAL cannot read PDFs |
| CRS handling | **rasterio.warp** | Reprojection to WGS84 with densified edges |
| Geometry | none | A bbox polygon is five points; built by hand |
| Storage | **DuckDB** + CSV/GeoJSON exports | Local, zero setup, SQL for medallion layers |
| Viewer | **MapLibre GL JS** + static GeoJSON, OpenStreetMap tiles | Free, no API keys, runs from a local server |

All swappable. Local-only, no cloud needed. Standalone GDAL (`osgeo`), pyproj and shapely from the original plan turned out not to be needed.

---

## 7. Repo Structure

```
map-library-atlas/
├── README.md                  # front page: which guide to read, commands, setup
├── PROJECT_SCOPE.md
├── CLAUDE.md                  # working rules for Claude sessions
├── config.example.yaml        # maps_folder path, output paths
├── pyproject.toml
├── config/
│   ├── regions.csv            # reusable region boxes (committed)
│   ├── map_manifest.example.csv
│   └── map_manifest.csv       # personal, gitignored
├── src/atlas/
│   ├── cli.py                 # `atlas census`, `atlas add`, `atlas run`, `atlas view`
│   ├── config.py              # reads config.yaml
│   ├── census.py              # read-only folder report
│   ├── metadata.py            # reads raw metadata from inside a file
│   ├── library.py             # copy maps into the library, keep index.csv
│   ├── bronze.py              # scan library, hash, inventory
│   ├── manifest.py            # reads and maintains the manual CSVs
│   ├── silver.py              # resolve bbox, validate
│   ├── gold.py                # gold tables, GeoJSON and to-do list export
│   ├── pipeline.py            # runs bronze, silver, gold in order
│   └── server.py              # local web app: page, JSON API, label saving, previews
├── library/                   # gitignored: the atlas's copies of the maps + index.csv
├── data/                      # gitignored
│   ├── atlas.duckdb
│   ├── bronze/ silver/ gold/
├── viewer/
│   ├── index.html             # one page, two tabs
│   ├── style.css
│   ├── app.js                 # Globe tab: MapLibre, loads gold GeoJSON
│   ├── labels.js              # Label maps tab
│   └── add.js                 # Add maps tab
├── tests/
└── docs/
    ├── QUICKSTART.md
    ├── HOW_IT_WORKS.md
    └── DEVELOPER.md
```

`.gitignore`: `library/`, `data/`, `config.yaml`, `config/map_manifest.csv`, and map file types. **Never commit map files or personal paths.**

---

## 8. Build Phases

0. **Test subset:** done. A 26-map Wisconsin folder.
1. **Census:** done. `atlas census`.
2. **Bronze:** done. Folder scan, hashing, raw metadata capture, skip unchanged files.
3. **Silver:** done for manual boxes and region defaults, with validation and status flags. Embedded georeferencing is implemented but switched off.
4. **Gold:** done. GeoJSON export and needs-review list.
5. **Viewer:** done. Base map, bbox layer, click popup listing all maps under the point.
6. **Polish:** partly done. Docs, tests and incremental bronze exist. Open items are listed in `docs/DEVELOPER.md` section 12 (duplicates, same-named files in the manifest, multi-page PDFs, scale).
7. **Simpler intake (in progress, branch `simpler-map-intake`):** library folder and `atlas add` done; ready-made list of US places and several places per map done; a Label maps screen in the browser done (previews, tag places, choose footprint, rename, park, filter by place, save); an Add maps tab with drag and drop done (new maps arrive untagged by choice). Next: a double-click launcher, then bulk labelling. Publisher and source link, and other countries, come later.

**MVP done when:** I run one command and see rectangles for all my located maps on a global map, plus a list of the ones I still need to locate. **Met for the test folder** (`atlas run`, then `atlas view`). Not yet run on the full library.

---

## 9. Open Questions

- [x] Format breakdown? Test folder: 22 PDFs (16 GeoPDF), 3 JPG, 1 PNG. Full library not yet counted.
- [x] What share are georeferenced? 16 of 26 in the test folder.
- [x] Are there multi-page PDFs? Yes, three in the test folder. Treated as one map each for now.
- [x] Stack: Python + DuckDB + MapLibre confirmed (see Section 6 for what changed).
- [x] OS and GDAL: macOS; standalone GDAL not needed so far.
- [x] Viewer: a local web page, started with `atlas view`.
- [ ] How should multi-page PDFs be handled (one map per page)?
- [ ] Should approximate (region-default) boxes look different in the viewer?
- [x] How should a removed map be handled? Deleting it from `library/` drops it from the atlas.

---

## 10. Instructions for Claude (paste into a build session)

> I'm building **Map Library Atlas** per `PROJECT_SCOPE.md`. Work one small step at a time. For each step: propose it in plain language, wait for my go-ahead, implement only that, add tests, update the docs, and show me how to check the result myself. Keep the pipeline idempotent (re-runs skip unchanged files by hash). Never modify or move source map files. Flag problem maps with a `status` instead of dropping them. Ask me before changing the schemas in Section 5 or the stack in Section 6.
