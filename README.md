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

## The four commands

Run from the project folder.

```bash
.venv/bin/atlas census -v
```

Counts the maps in a folder and prints a report. Changes nothing.

```bash
.venv/bin/atlas add "/path/to/maps"
```

Copies maps (a file or a whole folder) into the atlas's library. Your originals are not touched.

```bash
.venv/bin/atlas run
```

Rebuilds the list of maps, their boxes, and the files the globe reads, from the library.

```bash
.venv/bin/atlas view
```

Opens the globe in your browser. Press Ctrl+C in the terminal to stop it.

## The one rule

- `config/` is yours to edit. `config/map_manifest.csv` is where you say where each map belongs.
- `library/` holds the atlas's copies of your maps. Add with `atlas add`; delete a file to remove a map.
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

Then add your maps with `.venv/bin/atlas add` and run `.venv/bin/atlas run`.

## Privacy

`library/`, `data/`, `config.yaml` and `config/map_manifest.csv` are gitignored, as are map file
types. Source map files are never modified or moved.
