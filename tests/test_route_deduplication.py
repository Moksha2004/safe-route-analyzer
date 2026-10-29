from app.agents.agent1_route_engine import _route_signature


def test_identical_route_geometries_share_a_signature():
    route = [[77.60, 12.90], [77.61, 12.91], [77.62, 12.92]]
    duplicate = [[77.60, 12.90], [77.61, 12.91], [77.62, 12.92]]
    assert _route_signature(route) == _route_signature(duplicate)


def test_distinct_route_geometries_have_distinct_signatures():
    first = [[77.60, 12.90], [77.61, 12.91], [77.62, 12.92]]
    alternative = [[77.60, 12.90], [77.615, 12.915], [77.62, 12.92]]
    assert _route_signature(first) != _route_signature(alternative)
