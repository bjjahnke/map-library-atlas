import json

import numpy as np
import pytest
import rasterio
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject
from rasterio.transform import from_origin

from atlas.census import format_report, inspect_file, run_census
from atlas.cli import main

PIXELS = np.zeros((1, 4, 4), dtype="uint8")
WORLD_FILE = "0.1\n0\n0\n-0.1\n-90.0\n44.0\n"


def write_raster(path, driver, **georef):
    with rasterio.open(path, "w", driver=driver, width=4, height=4, count=1, dtype="uint8", **georef) as dst:
        dst.write(PIXELS)


def write_pdf(path, pages=1, geo=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=200, height=200)
        if geo:
            measure = DictionaryObject({NameObject("/Subtype"): NameObject("/GEO")})
            viewport = DictionaryObject({NameObject("/Measure"): measure})
            page[NameObject("/VP")] = ArrayObject([viewport])
    with open(path, "wb") as fh:
        writer.write(fh)


@pytest.fixture
def maps_folder(tmp_path):
    folder = tmp_path / "maps"
    (folder / "sub").mkdir(parents=True)
    write_raster(folder / "geo.tif", "GTiff", crs="EPSG:32616", transform=from_origin(300000, 4900000, 30, 30))
    write_raster(folder / "plain.tif", "GTiff")
    write_raster(folder / "sidecar.tif", "GTiff")
    (folder / "sidecar.tfw").write_text(WORLD_FILE)
    write_raster(folder / "sub" / "world.png", "PNG")
    (folder / "sub" / "world.pgw").write_text(WORLD_FILE)
    write_raster(folder / "plain.jpg", "JPEG")
    write_pdf(folder / "plain.pdf")
    write_pdf(folder / "sub" / "atlas.pdf", pages=3)
    write_pdf(folder / "geo.pdf", geo=True)
    (folder / "broken.pdf").write_bytes(b"not a pdf")
    (folder / "notes.txt").write_text("not a map")
    (folder / ".hidden.png").write_bytes(b"")
    return folder


def by_name(census):
    return {f["path"].rsplit("/", 1)[-1]: f for f in census["files"]}


def test_classifies_each_file(maps_folder):
    files = by_name(run_census(maps_folder))

    assert (files["geo.tif"]["format"], files["geo.tif"]["georef_method"]) == ("geotiff", "embedded")
    assert files["geo.tif"]["crs"] == "EPSG:32616"
    assert (files["plain.tif"]["format"], files["plain.tif"]["georef_method"]) == ("tiff", "none")
    assert (files["sidecar.tif"]["format"], files["sidecar.tif"]["georef_method"]) == ("tiff", "worldfile")
    assert (files["world.png"]["format"], files["world.png"]["georef_method"]) == ("png", "worldfile")
    assert (files["plain.jpg"]["format"], files["plain.jpg"]["georef_method"]) == ("jpg", "none")
    assert (files["plain.pdf"]["format"], files["plain.pdf"]["georef_method"]) == ("pdf", "none")
    assert (files["geo.pdf"]["format"], files["geo.pdf"]["georef_method"]) == ("geopdf", "embedded")
    assert files["atlas.pdf"]["pages"] == 3
    assert files["geo.tif"]["width_px"] == 4


def test_summary_counts(maps_folder):
    census = run_census(maps_folder)

    assert census["total_maps"] == 9
    assert census["georeferenced"] == 4
    assert census["not_georeferenced"] == 4
    assert census["errors"] == 1
    assert census["multi_page_pdfs"] == 1
    assert census["by_format"]["pdf"] == {
        "total": 3, "georeferenced": 0, "embedded": 0, "worldfile": 0, "errors": 1,
    }
    assert census["by_format"]["geopdf"]["total"] == 1
    # world files and hidden files are neither maps nor "ignored" noise
    assert census["ignored_extensions"] == {".txt": 1}


def test_unreadable_file_is_flagged_not_dropped(maps_folder):
    broken = by_name(run_census(maps_folder))["broken.pdf"]
    assert broken["status"] == "error"
    assert broken["status_detail"]


def test_non_map_file_returns_none(maps_folder):
    assert inspect_file(maps_folder / "notes.txt") is None


def test_census_does_not_touch_source_files(maps_folder):
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in maps_folder.rglob("*") if p.is_file()}
    run_census(maps_folder)
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in maps_folder.rglob("*") if p.is_file()}
    assert before == after


def test_missing_folder_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        run_census(tmp_path / "nope")


def test_report_text(maps_folder):
    report = format_report(run_census(maps_folder), verbose=True)
    assert "geotiff" in report
    assert "Multi-page PDFs:    1" in report
    assert "broken.pdf" in report


def test_cli_folder_flag_and_json(maps_folder, capsys):
    assert main(["census", "--folder", str(maps_folder), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total_maps"] == 9


def test_cli_reads_config(maps_folder, tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(f"maps_folder: {maps_folder}\n")
    assert main(["--config", str(config), "census"]) == 0
    assert "Census of" in capsys.readouterr().out


def test_cli_missing_config(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "missing.yaml"), "census"]) == 2
    assert "config.example.yaml" in capsys.readouterr().err
