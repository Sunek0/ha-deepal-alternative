"""Tests for the vehicle position helper."""

from deepal.location import find_location


def test_finds_flat_and_nested_coordinates():
    assert find_location({"lat": 41.65, "lng": -0.89}) == (41.65, -0.89)
    assert find_location(
        {"location": {"Latitude": "41.65", "Longitude": "-0.89"}}
    ) == (41.65, -0.89)
    assert find_location({"data": {"position": {"lat": 41.65, "lon": -0.89}}}) == (
        41.65,
        -0.89,
    )


def test_pairs_coordinates_from_the_same_object():
    assert find_location({"a": {"lat": 41.65}, "b": {"lng": -0.89}}) is None
    assert find_location(
        {"a": {"lat": 41.65}, "b": {"lat": 41.0, "lng": -0.89}}
    ) == (41.0, -0.89)


def test_discards_invalid_coordinates():
    assert find_location({"lat": 0, "lng": 0}) is None
    assert find_location({"lat": 91, "lng": 10}) is None
    assert find_location({"lat": 10, "lng": 181}) is None
    assert find_location({"lat": "abc", "lng": 10}) is None
    assert find_location({"lat": 0, "lon": 0, "nested": {"lat": 41.0, "lng": -0.89}}) == (
        41.0,
        -0.89,
    )


def test_searches_sources_in_order():
    assert find_location({"no": "position"}, {"lat": 41.0, "lng": -0.89}) == (
        41.0,
        -0.89,
    )
    assert find_location({}, None, []) is None


def test_respects_the_depth_limit():
    root: dict = {}
    current = root
    for _ in range(8):
        child: dict = {}
        current["child"] = child
        current = child
    current["lat"] = 41.0
    current["lng"] = -0.89

    assert find_location(root) is None
