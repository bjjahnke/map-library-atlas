# Quick start: adding maps to the atlas

For anyone who just wants to get maps onto the globe. No technical background needed.
For the full explanation of what happens behind the scenes, see
[HOW_IT_WORKS.md](HOW_IT_WORKS.md).

All commands are typed in a terminal, from the project folder.

---

## The short version

1. Run `.venv/bin/atlas add "/path/to/new/maps"` (a file or a whole folder).
2. Run `.venv/bin/atlas run`
3. Open `config/map_manifest.csv` and fill in the new rows at the bottom.
4. Run `.venv/bin/atlas run` again.
5. Run `.venv/bin/atlas view` to see them on the globe.

That's it. The rest of this page explains each step.

---

## Step by step

### 1. Add the maps to the library

Your maps can be anywhere on your computer, in any folders. Point the atlas at a single
file, several files, or a whole folder (it looks inside sub-folders too):

```bash
.venv/bin/atlas add "/path/to/new/maps"
```

Tip: type `.venv/bin/atlas add ` and then drag the file or folder from Finder into the
terminal window. That fills in the path for you.

The atlas copies each map into its own `library/` folder. Your originals are never
changed, moved or renamed. It prints what happened:

```
Added to the library:   3
Already in the library: 26     <- maps it already had are skipped, so re-adding is harmless
```

Accepted file types: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`.

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
| The map covers a whole state | the state's key, e.g. `wisconsin` or `new_york` | `region_key` |
| The map covers several states | the keys separated by semicolons, e.g. `new_york; connecticut; new_jersey` | `region_key` |
| The map covers the whole country | `contiguous_united_states` (lower 48) or `united_states` (all 50) | `region_key` |
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

## Places you can use

Every US state, DC and five territories are already defined in **`config/regions.csv`**,
along with `contiguous_united_states` and `united_states`. The key is the name in lower
case with underscores for spaces: `iowa`, `north_dakota`, `district_of_columbia`.

A map labelled with several places gets one box drawn around all of them. Maps placed
this way are treated as "approximate", because the box is the place's, not the map's own.

### Adding a place of your own

For anything not on the list (a county, a city, another country), add a row to
`config/regions.csv`:

```
buffalo_county_wi,Buffalo County WI,-92.08,44.02,-91.52,44.60
```

(Those numbers are only an illustration; look up the real ones.) Keep the key short,
lower-case, with no spaces. Then use it in `region_key` like any other.

---

## Changing something later

| To... | Do this, then run `.venv/bin/atlas run` |
|---|---|
| Rename a map | Type the new name in `title` in the notes file. |
| Move a map from a region box to its own box | Fill in the four box columns. Your own box wins over the region. |
| Park a map for later | Type `yes` in `revisit`. |
| Un-park a map | Clear the `revisit` cell. |
| See what still needs doing | Open `data/gold/needs_review.csv`. |
| Remove a map from the atlas | Delete its file from the `library/` folder. |

Never edit the files inside `data/`. They are rebuilt on every run and your changes
would be lost. Don't rename files inside `library/` either; add and delete only.

---

## Starting over with an empty atlas

Delete everything inside `library/` and delete the file `data/atlas.duckdb`, then add
maps again. Both are made by the atlas. Your original maps and your notes file are not
affected.

---

## If something looks wrong

| What you see | Likely cause | Fix |
|---|---|---|
| A map isn't on the globe | It has no box, or its row has a mistake. | Open `data/gold/needs_review.csv` and read its `status_detail`. |
| "the box in the manifest is incomplete" | Only some of the four box numbers are filled in. | Fill in all four, or clear all four. |
| "has a value that is not a number" | A letter or stray character in a box column. | Retype the number. |
| "region '...' is not in regions.csv" | The key is misspelled or not defined. Spaces must be underscores (`new_york`). | Fix the spelling, or add the place. |
| "bounding box has no area" | West/east or south/north are swapped. | Swap them back. Remember US longitudes are negative. |
| "latitude outside..." or "longitude outside..." | Latitude and longitude are in each other's columns. | `lon` columns hold the east-west numbers, `lat` the north-south ones. |
| `atlas run` says the library is empty | No maps have been added yet. | `.venv/bin/atlas add <file or folder>` |
| `atlas add` says "Not found" | The path is mistyped. | Drag the file or folder into the terminal instead of typing it. |
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

Then add your first maps as described at the top of this page.
