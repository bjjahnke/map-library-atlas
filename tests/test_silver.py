import csv

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject
from rasterio.warp import transform

from atlas.bronze import build_inventory
from atlas.metadata import read_raw_metadata
from atlas.silver import build_silver, clean_title, export_csv, resolve_map


def viewport(gpts, epsg, kind, bbox=(10, 190, 190, 10)):
    gcs = DictionaryObject({NameObject("/Type"): NameObject(kind), NameObject("/EPSG"): NumberObject(epsg)})
    measure = DictionaryObject(
        {
            NameObject("/Subtype"): NameObject("/GEO"),
            NameObject("/GPTS"): ArrayObject(FloatObject(v) for v in gpts),
            NameObject("/GCS"): gcs,
        }
    )
    return DictionaryObject(
        {NameObject("/BBox"): ArrayObject(FloatObject(v) for v in bbox), NameObject("/Measure"): measure}
    )


def write_pdf(path, viewports=()):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if viewports:
        page[NameObject("/VP")] = ArrayObject(viewports)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


REGIONS = {
    "wisconsin": {"min_lon": "-92.9", "min_lat": "42.5", "max_lon": "-86.8", "max_lat": "47.1"},
    "minnesota": {"min_lon": "-97.2", "min_lat": "43.5", "max_lon": "-89.5", "max_lat": "49.4"},
    "iowa": {"min_lon": "-96.6", "min_lat": "40.4", "max_lon": "-90.1", "max_lat": "43.5"},
}


def resolve(path, manual=None, use_embedded=True):
    extension = path.suffix.lstrip(".").lower()
    return resolve_map("abc", path.name, extension, read_raw_metadata(path), manual, REGIONS, use_embedded)


def box(row):
    return (row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"])


# lat, lon ring: lower-left, upper-left, upper-right, lower-right
GEOGRAPHIC_GPTS = [42.0, -93.0, 47.0, -93.0, 47.0, -87.0, 42.0, -87.0]


def test_geographic_viewport_gives_its_own_box(tmp_path):
    row = resolve(write_pdf(tmp_path / "state_map.pdf", [viewport(GEOGRAPHIC_GPTS, 4326, "/GEOGCS")]))
    assert (row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"]) == (-93.0, 42.0, -87.0, 47.0)
    assert row["status"] == "ok"
    assert (row["format"], row["georef_method"], row["bbox_source"], row["bbox_precision"]) == (
        "geopdf", "embedded", "embedded", "exact",
    )
    assert row["source_crs"] == "EPSG:4326"
    assert row["is_georeferenced"] is True


def test_projected_viewport_is_densified(tmp_path):
    # A rectangle in UTM 16N, far from the central meridian so its edges bow in lat/lon.
    xs, ys = [200000, 200000, 800000, 800000], [4700000, 5200000, 5200000, 4700000]
    lons, lats = transform("EPSG:32616", "EPSG:4326", xs, ys)
    gpts = [v for pair in zip(lats, lons) for v in pair]
    row = resolve(write_pdf(tmp_path / "utm.pdf", [viewport(gpts, 32616, "/PROJCS")]))

    assert row["status"] == "ok"
    assert row["source_crs"] == "EPSG:32616"
    assert row["min_lon"] == pytest.approx(min(lons), abs=1e-5)
    assert row["max_lon"] == pytest.approx(max(lons), abs=1e-5)
    # the top edge bulges north of both top corners; corners alone would miss it
    assert row["max_lat"] > max(lats) + 0.01


def test_largest_viewport_wins_over_insets(tmp_path):
    inset = viewport([10.0, 10.0, 11.0, 10.0, 11.0, 11.0, 10.0, 11.0], 4326, "/GEOGCS", bbox=(0, 20, 20, 0))
    main = viewport(GEOGRAPHIC_GPTS, 4326, "/GEOGCS")
    row = resolve(write_pdf(tmp_path / "insets.pdf", [inset, main]))
    assert row["min_lon"] == -93.0
    assert "2 georeferenced areas" in row["status_detail"]


def test_plain_files_need_a_location(tmp_path):
    row = resolve(write_pdf(tmp_path / "plain.pdf"))
    assert (row["status"], row["format"], row["bbox_source"]) == ("needs_georef", "pdf", "none")
    assert row["min_lon"] is None and row["is_georeferenced"] is False


def test_unreadable_file_is_an_error_not_dropped(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf")
    row = resolve(path)
    assert row["status"] == "error" and row["status_detail"]


def test_invalid_box_is_flagged(tmp_path):
    gpts = [95.0, -93.0, 97.0, -93.0, 97.0, -87.0, 95.0, -87.0]
    row = resolve(write_pdf(tmp_path / "bad.pdf", [viewport(gpts, 4326, "/GEOGCS")]))
    assert row["status"] == "error"


MANUAL_BOX = {"min_lon": "-89.6", "min_lat": "42.98", "max_lon": "-89.15", "max_lat": "43.2"}


def test_manual_box_is_used_and_exact(tmp_path):
    row = resolve(write_pdf(tmp_path / "plain.pdf"), MANUAL_BOX | {"title": "Madison Area"})
    assert box(row) == (-89.6, 42.98, -89.15, 43.2)
    assert (row["status"], row["bbox_source"], row["bbox_precision"]) == ("ok", "manual_override", "exact")
    assert row["title"] == "Madison Area"


def test_region_key_gives_region_box_marked_approximate(tmp_path):
    row = resolve(write_pdf(tmp_path / "plain.pdf"), {"region_key": " Wisconsin".strip()})
    assert box(row) == (-92.9, 42.5, -86.8, 47.1)
    assert (row["status"], row["bbox_source"], row["bbox_precision"]) == ("ok", "region_default", "approximate")
    assert row["region_key"] == "wisconsin"


def test_several_regions_give_one_box_around_all_of_them(tmp_path):
    row = resolve(write_pdf(tmp_path / "plain.pdf"), {"region_key": "Wisconsin; minnesota ;iowa"})
    assert box(row) == (-97.2, 40.4, -86.8, 49.4)
    assert (row["status"], row["bbox_source"], row["bbox_precision"]) == ("ok", "region_default", "approximate")
    assert row["region_key"] == "wisconsin; minnesota; iowa"

    typo = resolve(write_pdf(tmp_path / "plain.pdf"), {"region_key": "wisconsin; narnia"})
    assert typo["status"] == "error" and "narnia" in typo["status_detail"]


def test_manual_box_beats_region_and_embedded(tmp_path):
    path = write_pdf(tmp_path / "geo.pdf", [viewport(GEOGRAPHIC_GPTS, 4326, "/GEOGCS")])
    row = resolve(path, MANUAL_BOX | {"region_key": "wisconsin"})
    assert row["bbox_source"] == "manual_override" and box(row)[0] == -89.6


def test_embedded_location_is_ignored_unless_switched_on(tmp_path):
    path = write_pdf(tmp_path / "geo.pdf", [viewport(GEOGRAPHIC_GPTS, 4326, "/GEOGCS")])

    untouched = resolve(path, use_embedded=False)
    assert (untouched["status"], untouched["bbox_source"], untouched["min_lon"]) == ("needs_georef", "none", None)
    # the file's own georeferencing is still recorded as a fact
    assert (untouched["format"], untouched["is_georeferenced"], untouched["georef_method"]) == ("geopdf", True, "embedded")

    with_region = resolve(path, {"region_key": "wisconsin"}, use_embedded=False)
    assert with_region["bbox_source"] == "region_default"


def test_manifest_mistakes_are_flagged(tmp_path):
    path = write_pdf(tmp_path / "plain.pdf")
    partial = resolve(path, {"min_lon": "-89.6", "min_lat": "42.98"})
    assert partial["status"] == "error" and "incomplete" in partial["status_detail"]
    not_a_number = resolve(path, MANUAL_BOX | {"max_lat": "north"})
    assert not_a_number["status"] == "error" and "not a number" in not_a_number["status_detail"]
    unknown = resolve(path, {"region_key": "narnia"})
    assert unknown["status"] == "error" and "narnia" in unknown["status_detail"]
    swapped = resolve(path, MANUAL_BOX | {"min_lat": "43.2", "max_lat": "42.98"})
    assert swapped["status"] == "error"


def test_places_are_tags_and_the_footprint_is_a_separate_choice(tmp_path):
    path = write_pdf(tmp_path / "plain.pdf")

    # tagged Wisconsin, but the statewide rectangle would be wrong for it
    tagged = resolve(path, {"region_key": "wisconsin", "footprint": "none", "revisit": "yes", "notes": "Buffalo County"})
    assert (tagged["status"], tagged["bbox_source"], tagged["min_lon"]) == ("needs_georef", "none", None)
    assert tagged["region_key"] == "wisconsin"  # the tag is kept
    assert tagged["status_detail"] == "marked to come back to: Buffalo County; tagged only; no footprint yet"

    own = resolve(path, MANUAL_BOX | {"region_key": "wisconsin", "footprint": "own"})
    assert (own["bbox_source"], box(own), own["region_key"]) == ("manual_override", (-89.6, 42.98, -89.15, 43.2), "wisconsin")

    waiting = resolve(path, {"region_key": "wisconsin", "footprint": "own"})
    assert waiting["status"] == "needs_georef" and "none has been entered" in waiting["status_detail"]

    # "places" ignores a leftover own box
    around = resolve(path, MANUAL_BOX | {"region_key": "wisconsin", "footprint": "places"})
    assert (around["bbox_source"], box(around)) == ("region_default", (-92.9, 42.5, -86.8, 47.1))

    # rows from before the column existed behave as they always did
    assert resolve(path, MANUAL_BOX | {"region_key": "wisconsin"})["bbox_source"] == "manual_override"
    assert resolve(path, {"region_key": "wisconsin"})["bbox_source"] == "region_default"


def test_revisit_mark(tmp_path):
    path = write_pdf(tmp_path / "plain.pdf")

    parked = resolve(path, {"revisit": "yes", "notes": "which county?"})
    assert parked["status"] == "needs_georef"
    assert parked["status_detail"] == "marked to come back to: which county?"

    placeholder = resolve(path, {"revisit": "x", "region_key": "wisconsin"})
    assert (placeholder["status"], placeholder["bbox_source"]) == ("ok", "region_default")
    assert placeholder["status_detail"] == "marked to come back to"

    assert resolve(path, {"revisit": "no"})["status_detail"] == "no places or footprint yet"


def test_clean_title():
    assert clean_title("Wisconsin_map.jpg") == "Wisconsin map"
    assert clean_title("frac-sand-map_10-2013.png") == "frac sand map 10 2013"


def test_build_and_export(tmp_path):
    folder = tmp_path / "maps"
    folder.mkdir()
    write_pdf(folder / "geo.pdf", [viewport(GEOGRAPHIC_GPTS, 4326, "/GEOGCS")])
    write_pdf(folder / "plain.pdf")
    db, out = tmp_path / "atlas.duckdb", tmp_path / "silver" / "maps.csv"
    build_inventory(folder, db)

    assert build_silver(db) == {"total": 2, "ok": 0, "needs_georef": 2, "error": 0, "revisit": 0}
    manifest = [{"file_name": "plain.pdf", "region_key": "wisconsin"}]
    assert build_silver(db, manifest, REGIONS) == {"total": 2, "ok": 1, "needs_georef": 1, "error": 0, "revisit": 0}
    assert build_silver(db, manifest, REGIONS, use_embedded=True)["ok"] == 2
    assert export_csv(db, out) == 2  # re-running does not duplicate rows
    rows = {r["file_name"]: r for r in csv.DictReader(out.open())}
    assert rows["geo.pdf"]["max_lat"] == "47.0"
    assert rows["plain.pdf"]["bbox_source"] == "region_default"
