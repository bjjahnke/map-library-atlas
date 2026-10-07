# Map Library Atlas

A geospatial index of a local map collection (PDFs and images). Each map gets a
bounding box, and the boxes are drawn on a globe. Click a spot to list every map
covering it.

**Status:** working end to end on a small test folder.

## Which guide do I want?

| I want to... | Read |
|---|---|
| Add maps to the atlas, quickly | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| Understand what happens at each step, in plain language | [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) |
| See the technical detail: schemas, rules, modules, limitations | [docs/DEVELOPER.md](docs/DEVELOPER.md) |
| See the project plan and what's left to do | [PROJECT_SCOPE.md](PROJECT_SCOPE.md) |

## The three commands

Run from the project folder.

```bash
.venv/bin/atlas census -v
```

Counts the maps in your folder and prints a report. Changes nothing.

```bash
.venv/bin/atlas run
```

Rebuilds the list of maps, their boxes, and the files the globe reads.

```bash
.venv/bin/atlas view
```

Opens the globe in your browser. Press Ctrl+C in the terminal to stop it.

## The one rule

- `config/` is yours to edit. `config/map_manifest.csv` is where you say where each map belongs.
- `data/` is rebuilt by the tool on every run. Don't edit it by hand.

## First-time setup

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install --only-binary rasterio -e ".[dev]"
```

```bash
cp config.example.yaml config.yaml
```

Then set `maps_folder` in `config.yaml` to the folder holding your maps.

## Privacy

`data/`, `config.yaml` and `config/map_manifest.csv` are gitignored, as are map file
types. Source map files are never modified or moved.
