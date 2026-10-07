import json
import threading
from pathlib import Path
import urllib.error
import urllib.request

import pytest
from pypdf import PdfWriter

from atlas import server
from atlas.library import add_maps
from atlas.manifest import load_manifest


def write_pdf(path, width):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=200)
    with open(path, "wb") as fh:
        writer.write(fh)


@pytest.fixture
def atlas(tmp_path):
    source = tmp_path / "downloads"
    source.mkdir()
    write_pdf(source / "one.pdf", 100)
    write_pdf(source / "two.pdf", 110)
    regions = tmp_path / "regions.csv"
    regions.write_text(
        "region_key,region_name,min_lon,min_lat,max_lon,max_lat\n"
        "wisconsin,Wisconsin,-92.9,42.5,-86.8,47.1\n"
        "iowa,Iowa,-96.6,40.4,-90.1,43.5\n"
    )
    config = {
        "library_dir": str(tmp_path / "library"),
        "data_dir": str(tmp_path / "data"),
        "manifest_csv": str(tmp_path / "map_manifest.csv"),
        "regions_csv": str(regions),
    }
    add_maps([source], tmp_path / "library")
    app = server.make_server(config, 0)
    threading.Thread(target=app.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{app.server_port}", config
    app.shutdown()
    app.server_close()


def get(url):
    with urllib.request.urlopen(url) as response:
        return response.status, response.read()


def post(url, payload, headers=None):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"} | (headers or {})
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_state_lists_maps_and_places(atlas):
    base, _ = atlas
    state = json.loads(get(f"{base}/api/state")[1])
    assert [m["file_name"] for m in state["maps"]] == ["one.pdf", "two.pdf"]
    assert all(m["status"] == "needs_georef" and m["regions"] == [] for m in state["maps"])
    assert state["regions"] == [{"key": "wisconsin", "name": "Wisconsin"}, {"key": "iowa", "name": "Iowa"}]


def test_saving_labels_updates_the_manifest_and_the_globe(atlas):
    base, config = atlas
    one, two = json.loads(get(f"{base}/api/state")[1])["maps"]
    changes = {
        one["id"]: {"title": "Map One", "regions": ["wisconsin", "Iowa"]},
        two["id"]: {"revisit": True, "notes": "check later"},
    }
    status, state = post(f"{base}/api/save", {"changes": changes})

    assert status == 200 and state["updated"] == 2 and state["on_globe"] == 1
    saved_one, saved_two = state["maps"]
    assert (saved_one["title"], saved_one["regions"], saved_one["status"]) == ("Map One", ["wisconsin", "iowa"], "ok")
    assert (saved_two["revisit"], saved_two["notes"], saved_two["status"]) == (True, "check later", "needs_georef")
    assert {r["file_name"]: r["region_key"] for r in load_manifest(Path(config["manifest_csv"]))} == {
        "one.pdf": "wisconsin; iowa", "two.pdf": "",
    }

    features = json.loads(get(f"{base}/data/gold/map_library.geojson")[1])["features"]
    assert [f["properties"]["title"] for f in features] == ["Map One"]
    ring = features[0]["geometry"]["coordinates"][0]
    assert ring[0] == [-96.6, 40.4] and ring[2] == [-86.8, 47.1]  # one box around both states

    # clearing the places takes it back off the globe
    status, state = post(f"{base}/api/save", {"changes": {one["id"]: {"regions": []}}})
    assert state["on_globe"] == 0


def test_footprint_choice_is_saved_separately_from_places(atlas):
    base, _ = atlas
    one, two = json.loads(get(f"{base}/api/state")[1])["maps"]
    assert (one["footprint"], one["box"]) == ("places", ["", "", "", ""])

    changes = {
        one["id"]: {"regions": ["wisconsin"], "footprint": "none"},
        two["id"]: {"regions": ["wisconsin"], "footprint": "own", "box": ["-91.9", "44.0", "-91.5", "44.6"]},
    }
    _, state = post(f"{base}/api/save", {"changes": changes})
    tagged, own = state["maps"]
    assert (tagged["regions"], tagged["footprint"], tagged["status"]) == (["wisconsin"], "none", "needs_georef")
    assert (own["footprint"], own["box"], own["status"], own["bbox_precision"]) == (
        "own", ["-91.9", "44.0", "-91.5", "44.6"], "ok", "exact",
    )
    assert state["on_globe"] == 1

    _, state = post(f"{base}/api/save", {"changes": {two["id"]: {"box": ["-91.9", "44.6", "-91.5", "44.0"]}}})
    assert state["maps"][1]["status"] == "error"  # south above north is reported, not hidden


def upload(base, name, data, path=""):
    from urllib.parse import quote

    request = urllib.request.Request(
        f"{base}/api/add?name={quote(name)}&path={quote(path)}", data=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["result"]


def test_adding_maps_from_the_browser(atlas, tmp_path):
    base, config = atlas
    new_map = tmp_path / "three.pdf"
    write_pdf(new_map, 120)
    data = new_map.read_bytes()

    assert upload(base, "three & co.pdf", data, "Minnesota/three & co.pdf") == "added"
    assert upload(base, "same map again.pdf", data) == "already"
    assert upload(base, "notes.txt", b"hello") == "not_map"

    status, state = post(f"{base}/api/rebuild", {})
    assert status == 200
    names = [m["file_name"] for m in state["maps"]]
    assert names == ["one.pdf", "three & co.pdf", "two.pdf"]
    new = state["maps"][1]
    assert (new["regions"], new["status"]) == ([], "needs_georef")  # arrives untagged, for manual review
    assert len([p for p in Path(config["library_dir"]).iterdir() if p.suffix == ".pdf"]) == 3


def test_pages_files_and_refusals(atlas):
    base, _ = atlas
    one = json.loads(get(f"{base}/api/state")[1])["maps"][0]
    assert b"Label maps" in get(f"{base}/viewer/")[1]
    assert get(f"{base}/viewer/labels.js")[0] == 200
    assert get(f"{base}/api/file/{one['id']}")[1].startswith(b"%PDF")

    for path in ("/config.yaml", "/viewer/../config.yaml", "/api/file/unknown", "/data/atlas.duckdb"):
        with pytest.raises(urllib.error.HTTPError):
            get(base + path)
    status, body = post(f"{base}/api/save", {"changes": {}}, {"Origin": "https://example.com"})
    assert status == 403
