import csv

from atlas.bronze import build_inventory, read_inventory
from atlas.cli import main
from atlas.library import add_maps, original_names, read_index


def make_sources(tmp_path):
    source = tmp_path / "downloads"
    (source / "United States" / "Wisconsin").mkdir(parents=True)
    (source / "United States" / "Iowa").mkdir(parents=True)
    (source / "United States" / "Wisconsin" / "map.pdf").write_bytes(b"wisconsin map")
    (source / "United States" / "Iowa" / "map.pdf").write_bytes(b"iowa map")  # same name, different map
    (source / "roads.JPG").write_bytes(b"roads")
    (source / "roads copy.jpg").write_bytes(b"roads")  # same map, different name
    (source / "readme.txt").write_text("not a map")
    return source


def snapshot(folder):
    return {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in folder.rglob("*") if p.is_file()}


def test_add_copies_into_one_flat_folder(tmp_path):
    source, library = make_sources(tmp_path), tmp_path / "library"
    before = snapshot(source)

    result = add_maps([source], library)

    assert sorted(result["added"]) == ["map.pdf", "map.pdf", "roads copy.jpg"]
    assert result["already_in_library"] == 1  # the second copy of the roads map
    assert result["not_maps"] == 1
    files = sorted(p.name for p in library.iterdir() if p.name != "index.csv")
    assert len(files) == 3 and all(p.is_file() for p in library.iterdir())
    assert [name.split("__")[0] for name in files] == ["map", "map", "roads copy"]
    assert snapshot(source) == before  # originals untouched


def test_adding_again_adds_nothing(tmp_path):
    source, library = make_sources(tmp_path), tmp_path / "library"
    add_maps([source], library)
    again = add_maps([source, source / "roads.JPG"], library)
    assert again["added"] == [] and again["already_in_library"] == 5
    assert len(read_index(library)) == 3


def test_index_remembers_where_each_map_came_from(tmp_path):
    source, library = make_sources(tmp_path), tmp_path / "library"
    add_maps([source / "United States"], library)
    rows = list(csv.DictReader((library / "index.csv").open()))
    assert {r["original_name"] for r in rows} == {"map.pdf"}
    assert {r["original_path"].split("/")[-2] for r in rows} == {"Wisconsin", "Iowa"}
    assert all((library / r["library_name"]).is_file() and len(r["file_id"]) == 64 for r in rows)
    assert set(original_names(library).values()) == {"map.pdf"}


def test_missing_path_and_deleted_copy(tmp_path):
    source, library = make_sources(tmp_path), tmp_path / "library"
    result = add_maps([source / "roads.JPG", tmp_path / "nope"], library)
    assert result["missing"] == [tmp_path / "nope"]

    next(p for p in library.iterdir() if p.name != "index.csv").unlink()
    assert add_maps([source / "roads.JPG"], library)["added"] == ["roads.JPG"]  # copied back
    assert len(read_index(library)) == 1


def test_library_feeds_the_inventory_with_original_names(tmp_path):
    source, library, db = make_sources(tmp_path), tmp_path / "library", tmp_path / "atlas.duckdb"
    add_maps([source], library)
    counts = build_inventory(library, db, original_names(library))
    rows = read_inventory(db)
    assert counts["total"] == 3  # index.csv is not a map
    assert sorted(r["file_name"] for r in rows) == ["map.pdf", "map.pdf", "roads copy.jpg"]
    assert all(str(library.resolve()) in r["file_path"] for r in rows)


def test_cli_add_then_run(tmp_path, capsys):
    source = make_sources(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"library_dir: {tmp_path / 'library'}\ndata_dir: {tmp_path / 'data'}\n"
        f"manifest_csv: {tmp_path / 'config' / 'map_manifest.csv'}\n"
    )
    assert main(["--config", str(config), "add", str(source)]) == 0
    assert "Added to the library:   3" in capsys.readouterr().out
    assert main(["--config", str(config), "run"]) == 0
    assert "Maps in the library: 3" in capsys.readouterr().out
