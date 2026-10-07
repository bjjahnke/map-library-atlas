import csv

import pytest

from atlas.bronze import build_inventory, export_csv, read_inventory
from atlas.cli import main
from atlas.manifest import ensure_manifest, load_manifest, load_regions


@pytest.fixture
def maps_folder(tmp_path):
    folder = tmp_path / "maps"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.pdf").write_bytes(b"map a")
    (folder / "b.JPG").write_bytes(b"map b")
    (folder / "sub" / "a_copy.pdf").write_bytes(b"map a")
    (folder / "notes.txt").write_text("not a map")
    return folder


def test_inventory_lists_only_map_files(maps_folder, tmp_path):
    db = tmp_path / "data" / "atlas.duckdb"
    counts = build_inventory(maps_folder, db)
    rows = {r["file_name"]: r for r in read_inventory(db)}

    assert counts == {"new": 3, "changed": 0, "unchanged": 0, "total": 3, "removed": 0}
    assert set(rows) == {"a.pdf", "b.JPG", "a_copy.pdf"}
    assert rows["b.JPG"]["extension"] == "jpg"
    assert rows["a.pdf"]["size_bytes"] == 5
    assert len(rows["a.pdf"]["file_id"]) == 64
    assert "error" in rows["a.pdf"]["raw_metadata"]  # fixture files are not real PDFs


def test_duplicate_contents_share_a_file_id(maps_folder, tmp_path):
    db = tmp_path / "atlas.duckdb"
    build_inventory(maps_folder, db)
    rows = {r["file_name"]: r for r in read_inventory(db)}
    assert rows["a.pdf"]["file_id"] == rows["a_copy.pdf"]["file_id"] != rows["b.JPG"]["file_id"]


def test_rerun_skips_unchanged_and_picks_up_changes(maps_folder, tmp_path):
    db = tmp_path / "atlas.duckdb"
    build_inventory(maps_folder, db)
    first = {r["file_name"]: r for r in read_inventory(db)}

    assert build_inventory(maps_folder, db)["unchanged"] == 3
    assert {r["file_name"]: r for r in read_inventory(db)} == first

    (maps_folder / "b.JPG").write_bytes(b"map b, edited")
    (maps_folder / "c.png").write_bytes(b"map c")
    (maps_folder / "a.pdf").unlink()
    counts = build_inventory(maps_folder, db)
    rows = {r["file_name"]: r for r in read_inventory(db)}

    assert counts == {"new": 1, "changed": 1, "unchanged": 1, "total": 3, "removed": 1}
    assert rows["b.JPG"]["file_id"] != first["b.JPG"]["file_id"]
    assert "a.pdf" not in rows  # the list mirrors the folder


def test_original_names_are_recorded(maps_folder, tmp_path):
    db = tmp_path / "atlas.duckdb"
    build_inventory(maps_folder, db, {"a.pdf": "Original Name.pdf"})
    names = {r["file_name"] for r in read_inventory(db)}
    assert names == {"Original Name.pdf", "b.JPG", "a_copy.pdf"}


def test_source_files_are_untouched(maps_folder, tmp_path):
    snapshot = lambda: {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in maps_folder.rglob("*") if p.is_file()}
    before = snapshot()
    build_inventory(maps_folder, tmp_path / "atlas.duckdb")
    assert snapshot() == before


def test_export_csv(maps_folder, tmp_path):
    db, out = tmp_path / "atlas.duckdb", tmp_path / "bronze" / "file_inventory.csv"
    build_inventory(maps_folder, db)
    assert export_csv(db, out) == 3
    rows = list(csv.DictReader(out.open()))
    assert [r["file_name"] for r in rows] == ["a.pdf", "a_copy.pdf", "b.JPG"]
    assert rows[0]["size_bytes"] == "5"


def test_manifest_adds_blank_rows_and_keeps_edits(tmp_path):
    manifest = tmp_path / "config" / "map_manifest.csv"
    assert ensure_manifest(manifest, ["b.jpg", "a.pdf"]) == 2
    assert manifest.read_text().splitlines() == [
        "file_name,revisit,region_key,min_lon,min_lat,max_lon,max_lat,title,notes",
        "a.pdf,,,,,,,,",
        "b.jpg,,,,,,,,",
    ]

    edited = manifest.read_text().replace("a.pdf,,,,,,,,", "a.pdf,,wisconsin,,,,,My title,a note").rstrip("\n")
    manifest.write_text(edited)  # hand edit, saved without a trailing newline
    assert ensure_manifest(manifest, ["a.pdf", "b.jpg", "c.png"]) == 1
    assert ensure_manifest(manifest, ["a.pdf", "b.jpg", "c.png"]) == 0
    assert manifest.read_text().splitlines()[1:] == [
        "a.pdf,,wisconsin,,,,,My title,a note",
        "b.jpg,,,,,,,,",
        "c.png,,,,,,,,",
    ]


def test_manifest_gains_new_columns_without_losing_edits(tmp_path):
    manifest = tmp_path / "map_manifest.csv"
    manifest.write_text(
        "file_name,region_key,min_lon,min_lat,max_lon,max_lat,title,notes,my_own_column\n"
        'a.pdf,wisconsin,,,,,"Title, with comma","line one\nline two",keep me\n'
    )
    assert ensure_manifest(manifest, ["a.pdf"]) == 0
    assert manifest.read_text().splitlines()[0] == (
        "file_name,revisit,region_key,min_lon,min_lat,max_lon,max_lat,title,notes,my_own_column"
    )
    row = load_manifest(manifest)["a.pdf"]
    assert (row["revisit"], row["region_key"], row["title"]) == ("", "wisconsin", "Title, with comma")
    assert (row["notes"], row["my_own_column"]) == ("line one\nline two", "keep me")


def test_cli_run(maps_folder, tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"library_dir: {maps_folder}\ndata_dir: {tmp_path / 'data'}\n"
        f"manifest_csv: {tmp_path / 'config' / 'map_manifest.csv'}\n"
    )
    assert main(["--config", str(config), "run"]) == 0
    assert "Maps in the library: 3" in capsys.readouterr().out
    assert (tmp_path / "data" / "bronze" / "file_inventory.csv").is_file()
    assert (tmp_path / "config" / "map_manifest.csv").is_file()


def test_load_manual_files(tmp_path):
    manifest = tmp_path / "map_manifest.csv"
    # saved from a spreadsheet app: byte-order mark, Windows line endings, stray spaces
    manifest.write_bytes(
        "\ufefffile_name,region_key,min_lon,min_lat,max_lon,max_lat,title,notes\r\n"
        "a.pdf, Wisconsin ,,,,,,\r\n".encode()
    )
    assert load_manifest(manifest)["a.pdf"]["region_key"] == "Wisconsin"
    assert load_manifest(tmp_path / "missing.csv") == {}

    regions = tmp_path / "regions.csv"
    regions.write_text("region_key,region_name,min_lon,min_lat,max_lon,max_lat\nWisconsin,Wisconsin,-92.9,42.5,-86.8,47.1\n")
    assert load_regions(regions)["wisconsin"]["max_lat"] == "47.1"
