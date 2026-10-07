"""Checks on the shipped list of places in config/regions.csv."""

from pathlib import Path

from atlas.manifest import load_regions
from atlas.silver import BOX_FIELDS, _validate

REGIONS = load_regions(Path(__file__).parent.parent / "config" / "regions.csv")


def test_every_state_is_present():
    assert len(REGIONS) == 58  # 50 states, DC, 5 territories, and two whole-country entries
    for key in ("wisconsin", "new_york", "district_of_columbia", "alaska", "hawaii", "puerto_rico"):
        assert key in REGIONS
    assert {"united_states", "contiguous_united_states"} <= set(REGIONS)


def test_every_box_is_usable():
    for key, row in REGIONS.items():
        assert _validate(tuple(float(row[field]) for field in BOX_FIELDS)) is None, key


def test_country_boxes_contain_their_states():
    def box(key):
        return tuple(float(REGIONS[key][field]) for field in BOX_FIELDS)

    lower48, everything = box("contiguous_united_states"), box("united_states")
    for state in ("maine", "florida", "washington", "california", "texas"):
        s = box(state)
        assert lower48[0] <= s[0] and lower48[1] <= s[1] and lower48[2] >= s[2] and lower48[3] >= s[3]
    assert everything[0] <= box("alaska")[0] and everything[3] >= box("alaska")[3]
    assert lower48[3] < box("alaska")[1]  # the lower 48 stop south of Alaska
