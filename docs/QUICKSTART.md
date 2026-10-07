# Quick start: adding maps to the atlas

For anyone who just wants to get maps onto the globe. No technical background needed.
For the full explanation of what happens behind the scenes, see
[HOW_IT_WORKS.md](HOW_IT_WORKS.md).

All commands are typed in a terminal, from the project folder.

---

## The short version

1. Run `.venv/bin/atlas view`. The atlas opens in your browser.
2. Click the **Add maps** tab and drag your map files, or a folder of them, into the box.
3. Click the **Label maps** tab, tag each new map with its places, click **Save**.
4. Click the **Globe** tab to see them.

The rest of this page explains each step.

---

## Step by step

### 1. Open the atlas

```bash
.venv/bin/atlas view
```

Your browser opens the atlas. Leave the terminal window alone while you work; press
Ctrl+C in it when you're finished. This is the only command you need.

### 2. Add the maps

Click the **Add maps** tab. Your maps can be anywhere on your computer, in any folders.

- Drag files, or a whole folder, from Finder into the dashed box. Folders inside folders
  are fine.
- Or click **Choose files…** or **Choose a folder…** and pick them.

The atlas copies each map into its own library. Your originals are never changed, moved
or renamed. The page lists each file and what happened to it:

| It says | Meaning |
|---|---|
| Added | A new map, now in the library. |
| Already in the library | The atlas has this exact map, so it was skipped. Adding the same folder twice is harmless. |
| Could not be added | Something went wrong with that file; the reason is shown. |

Files that aren't maps are skipped. Accepted types: PDF, JPG, PNG, TIFF.

New maps arrive with no places and no footprint. Click **Label the new maps** to go
and tag them.

### 3. Label the new maps

On the **Label maps** tab, each map is a card with a preview. To find the new ones
quickly, click **Not on the globe** at the top, or choose "No places yet" in the list
next to it.

On each card:

| To... | Do this |
|---|---|
| Tag where a map is | Click "Add a place…", start typing a state, and pick it from the list. |
| Tag a map that covers several states | Add each one. Its footprint is one rectangle around all of them. |
| Tag a map without drawing the whole state (a county map, say) | Add the state, then set **Footprint on the globe** to "None yet". |
| Give a map its own exact rectangle | Set **Footprint on the globe** to "Its own rectangle" and fill in West, South, East, North. |
| Label a national map | Add "United States (lower 48)" or "United States (all 50 states)". |
| Remove a place | Click the × next to it. |
| Give the map a nicer name | Type it in **Title**. Leave it empty to use the file name. |
| Park a map you're unsure about | Tick **Come back to this one** and, if you like, add a note. |
| Look at the map properly | Click its preview. It opens in a new tab. |

Cards you've changed get an orange outline. Nothing is stored until you click **Save**
at the top right.

The first time you open this tab, previews take a second or two each to appear.

### 4. Look at the globe

Click the **Globe** tab. Click inside a box to list the maps there.

---

## Giving a map its own rectangle

On the map's card, set **Footprint on the globe** to "Its own rectangle". Four boxes
appear: West, South, East, North. Fill in all four and click Save. The map keeps its
place tags either way.

The four numbers are in degrees:

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

Everything in the table in step 3 works at any time: open the atlas, go to **Label
maps**, change the card, click **Save**.

| To... | Do this |
|---|---|
| See what still needs doing | Click **Not on the globe** or **Come back to** on the Label maps tab. |
| See only the maps in one state | Pick the state from the list at the top of the Label maps tab. |
| Un-park a map | Untick **Come back to this one** and Save. |
| Remove a map from the atlas | Delete its file from the `library/` folder, then reopen the atlas. |

Never edit the files inside `data/`. They are rebuilt automatically and your changes
would be lost. Don't rename files inside `library/` either; add and delete only.

---

## Starting over with an empty atlas

Delete everything inside `library/` and delete the file `data/atlas.duckdb`, then add
maps again. Both are made by the atlas. Your original maps and your labels are not
affected.

---

## If something looks wrong

| What you see | Likely cause | Fix |
|---|---|---|
| A map isn't on the globe | It has no places yet, or it's parked. | On the Label maps tab, click **Not on the globe** and add a place to it. |
| A card says "Problem" | Something is wrong with that map's labels or file; the reason is shown in red on the card. | Fix what it describes. The rows below explain the common ones. |
| A place shows in red as "not in the list" | The labels file names a place that isn't defined. | Remove it with the ×, or add the place to `config/regions.csv`. |
| Previews are blank boxes | Previews need a Mac; or that file can't be previewed. | The map still works; click the preview area to open the file. |
| "Could not load your maps" or "Could not save" | The atlas was stopped in the terminal. | Run `.venv/bin/atlas view` again and reload the page. |
| "the box in the manifest is incomplete" | Only some of the four box numbers are filled in. | Fill in all four, or clear all four. |
| "has a value that is not a number" | A letter or stray character in a box column. | Retype the number. |
| "region '...' is not in regions.csv" | The key is misspelled or not defined. Spaces must be underscores (`new_york`). | Fix the spelling, or add the place. |
| "bounding box has no area" | West/east or south/north are swapped. | Swap them back. Remember US longitudes are negative. |
| "latitude outside..." or "longitude outside..." | Latitude and longitude are in each other's columns. | `lon` columns hold the east-west numbers, `lat` the north-south ones. |
| There are no cards on the Label maps tab | No maps have been added yet. | `.venv/bin/atlas add <file or folder>` |
| Dropping a folder adds nothing | It contains no PDF, JPG, PNG or TIFF files. | Check the folder; the page says how many files it skipped. |
| I changed labels but nothing happened | Save wasn't clicked. | Changed cards have an orange outline; click **Save**. |
| The top bar says "No maps to show yet" | Nothing has a place yet, or the library is empty. | Add maps, then label them. |
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

Then open the atlas and add your first maps as described at the top of this page.
