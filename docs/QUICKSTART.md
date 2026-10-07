# Quick start: adding maps to the atlas

For anyone who just wants to get maps onto the globe. No technical background needed.
For the full explanation of what happens behind the scenes, see
[HOW_IT_WORKS.md](HOW_IT_WORKS.md).

All commands are typed in a terminal, from the project folder.

---

## The short version

1. Put the new map files in your maps folder.
2. Run `.venv/bin/atlas run`
3. Open `config/map_manifest.csv` and fill in the new rows at the bottom.
4. Run `.venv/bin/atlas run` again.
5. Run `.venv/bin/atlas view` to see them on the globe.

That's it. The rest of this page explains each step.

---

## Step by step

### 1. Put the map files in your maps folder

Copy or save the new maps into the folder the atlas scans. Sub-folders are fine; it
looks inside them too. The folder's location is the `maps_folder` line in `config.yaml`.

Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`.

The atlas never changes, moves or renames your map files.

### 2. Let the atlas notice them

```bash
.venv/bin/atlas run
```

Look for the line that says how many are new, for example `new: 3`. The atlas has now
added one blank row per new map to your notes file.

### 3. Tell the atlas where each new map belongs

Open **`config/map_manifest.csv`**. The new maps are the rows at the bottom with
nothing filled in. For each one, do **one** of these:

| If... | Then type... | In column(s)... |
|---|---|---|
| The map covers a whole region you've already defined | the region's key, e.g. `wisconsin` | `region_key` |
| You know the map's exact edges | west, south, east, north in degrees | `min_lon`, `min_lat`, `max_lon`, `max_lat` |
| You're not sure yet | `yes` (and a reminder in `notes` if you like) | `revisit` |

Optional: type a nicer name in `title`. Leave it blank and the file name is used.

Do not change the `file_name` column. It is how each row is matched to its map.

**Save the file as CSV.** In Numbers, use File > Export To > CSV. A normal save in
Numbers makes a different kind of file that the atlas cannot read.

### 4. Rebuild

```bash
.venv/bin/atlas run
```

Check the summary it prints:

```
Maps with a box:        27      <- these will be on the globe
Maps needing a location: 2      <- no box yet (includes parked maps)
Maps with a problem:     0      <- should be 0; see "If something looks wrong"
Marked to come back to:  2
```

### 5. Look at the globe

```bash
.venv/bin/atlas view
```

Your browser opens with the globe. Click inside a box to list the maps there. If the
globe was already open, just refresh the page. Press Ctrl+C in the terminal to stop
the viewer when you're done.

---

## Finding a map's exact edges

A box is four numbers, in degrees:

| Column | Which edge | Wisconsin, as an example |
|---|---|---|
| `min_lon` | West (left) | -92.89 |
| `min_lat` | South (bottom) | 42.49 |
| `max_lon` | East (right) | -86.81 |
| `max_lat` | North (top) | 47.08 |

Things that trip people up:

- In the United States, longitudes are **negative**.
- West is the smaller (more negative) longitude; south is the smaller latitude.
- Fill in all four numbers or none. Three out of four is treated as a mistake.

Ways to get the numbers: read them off the map's own margins if it prints coordinates;
or use a website that lets you draw a rectangle on a map and shows its corners
(bboxfinder.com is one). Whichever you use, check which order it lists the numbers in.

---

## Adding a new region

A region is a reusable box with a short name, so you don't have to retype the same four
numbers for every statewide (or countywide) map.

Open **`config/regions.csv`** and add a row:

```
region_key,region_name,min_lon,min_lat,max_lon,max_lat
wisconsin,Wisconsin,-92.888114,42.491983,-86.805415,47.080621
buffalo_county_wi,Buffalo County WI,-92.08,44.02,-91.52,44.60
```

(The Buffalo County numbers above are only an illustration; look up the real ones.)

Keep `region_key` short, lower-case, with no spaces. Then type that key in the
`region_key` column of your notes file for any map that covers the region, and run
`.venv/bin/atlas run`.

Maps placed by region are treated as "approximate", because the box is the region's,
not the map's own.

---

## Changing something later

| To... | Do this, then run `.venv/bin/atlas run` |
|---|---|
| Rename a map | Type the new name in `title` in the notes file. |
| Move a map from a region box to its own box | Fill in the four box columns. Your own box wins over the region. |
| Park a map for later | Type `yes` in `revisit`. |
| Un-park a map | Clear the `revisit` cell. |
| See what still needs doing | Open `data/gold/needs_review.csv`. |

Never edit the files inside `data/`. They are rebuilt on every run and your changes
would be lost.

---

## Scanning a different or bigger folder

Open `config.yaml` and change the `maps_folder` line to the folder you want.

- Pointing at a folder that **contains** the old one (for example moving up from
  `Wisconsin` to `United States`) just adds the extra maps. Your existing notes carry over.
- Pointing at a **completely different** folder keeps the old maps in the list too,
  because the atlas does not forget files it has seen. To start clean, delete the file
  `data/atlas.duckdb` and run `.venv/bin/atlas run`. That file is made by the atlas and
  is safe to delete; your notes file is not affected.

---

## If something looks wrong

| What you see | Likely cause | Fix |
|---|---|---|
| A map isn't on the globe | It has no box, or its row has a mistake. | Open `data/gold/needs_review.csv` and read its `status_detail`. |
| "the box in the manifest is incomplete" | Only some of the four box numbers are filled in. | Fill in all four, or clear all four. |
| "has a value that is not a number" | A letter or stray character in a box column. | Retype the number. |
| "region '...' is not in regions.csv" | The region key is misspelled or not defined. | Fix the spelling, or add the region. |
| "bounding box has no area" | West/east or south/north are swapped. | Swap them back. Remember US longitudes are negative. |
| "latitude outside..." or "longitude outside..." | Latitude and longitude are in each other's columns. | `lon` columns hold the east-west numbers, `lat` the north-south ones. |
| My notes seem to be ignored | The file wasn't saved as CSV, or wasn't saved at all. | Export as CSV over the original file, then run again. |
| Globe says "No map file found" | The atlas hasn't been run yet. | `.venv/bin/atlas run` |
| `atlas view` says it could not start | The viewer is already running in another terminal. | Use that one, or run `.venv/bin/atlas view --port 8001`. |
| The globe is blank or grey | No internet. The background map is downloaded as you look at it. | Reconnect and refresh. |
| `command not found` or `no such file` | The terminal isn't in the project folder, or setup hasn't been done. | Move to the project folder; see "First-time setup" below. |

---

## First-time setup

Only needed once per computer.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install --only-binary rasterio -e ".[dev]"
```

```bash
cp config.example.yaml config.yaml
```

Then open `config.yaml` and set `maps_folder` to the folder holding your maps.
