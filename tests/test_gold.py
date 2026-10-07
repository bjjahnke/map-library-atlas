import csv
import json

from pypdf import PdfWriter

from atlas.bronze import build_inventory
from atlas.gold import build_gold
from atlas.silver import build_silver

REGIONS = {"wisconsin": {"min_lon": "-92.9", "min_lat": "42.5", "max_lon": "-86.8", "max_lat": "47.1"}}


def write_pdf(path, width):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=200)  # different widths so contents differ
    with open(path, "wb") as fh:
        writer.write(fh)


def test_gold_outputs(tmp_path):
    folder = tmp_path / "maps"
    folder.mkdir()
    for width, name in enumerate(("located.pdf", "parked.pdf", "untouched.pdf"), start=100):
        write_pdf(folder / name, width)
    db = tmp_path / "atlas.duckdb"
    geojson, review = tmp_path / "gold" / "map_library.geojson", tmp_path / "gold" / "needs_review.csv"
    manifest = {
        "located.pdf": {"region_key": "wisconsin", "title": "My Map"},
        "parked.pdf": {"revisit": "yes", "notes": "which county?"},
    }
    build_inventory(folder, db)
    build_silver(db, manifest, REGIONS)

    assert build_gold(db, geojson, review) == {"located": 1, "needs_review": 2}
    assert build_gold(db, geojson, review) == {"located": 1, "needs_review": 2}  # re-runnable

    collection = json.loads(geojson.read_text())
    assert collection["type"] == "FeatureCollection"
    (feature,) = collection["features"]
    assert feature["properties"] == {"title": "My Map", "file_path": str((folder / "located.pdf").resolve())}
    assert feature["geometry"]["coordinates"] == [
        [[-92.9, 42.5], [-86.8, 42.5], [-86.8, 47.1], [-92.9, 47.1], [-92.9, 42.5]]
    ]

    rows = {r["title"]: r for r in csv.DictReader(review.open())}
    assert set(rows) == {"parked", "untouched"}
    assert rows["parked"]["status_detail"] == "marked to come back to: which county?"
    assert rows["untouched"]["status"] == "needs_georef"
