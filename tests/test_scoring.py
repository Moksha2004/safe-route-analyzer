from app.scoring.night_activity import score_night_activity
from app.scoring.ranking import rank_routes
from app.scoring.street_lighting import normalize_lamp_density
from app.scoring.weights import is_night_hour


def test_lighting_score_is_relative_to_alternatives():
    density = normalize_lamp_density([0, 4, 8], [1000, 1000, 1000])
    assert density == [(0.0, 0.0), (4.0, 50.0), (8.0, 100.0)]


def test_empty_lighting_is_zero():
    assert normalize_lamp_density([0, 0], [1000, 2000]) == [(0.0, 0.0), (0.0, 0.0)]


def test_night_score_includes_lighting_and_reweights_missing_signals():
    score, breakdown = score_night_activity({"streetLighting": 100, "policePresence": 50})
    assert score == 75.0
    assert breakdown["components"]["streetLighting"] == 100
    assert "nightTrafficActivity" in breakdown["missingSignals"]


def test_night_window_crosses_midnight():
    assert is_night_hour(20)
    assert is_night_hour(5)
    assert not is_night_hour(12)


def test_preference_match_can_outweigh_shortest_route():
    routes = [
        {"routeId": "short", "durationSeconds": 600, "trafficDelaySeconds": 0, "nightActivityScore": 0, "streetLightingScore": 0, "activitySummary": {}, "policeAdvantageScore": 0, "residentialCoveragePercent": 0, "preferenceScore": 0},
        {"routeId": "lake", "durationSeconds": 1200, "trafficDelaySeconds": 0, "nightActivityScore": 0, "streetLightingScore": 0, "activitySummary": {}, "policeAdvantageScore": 0, "residentialCoveragePercent": 0, "preferenceScore": 100},
    ]
    ranked = rank_routes(routes, is_night=False, mode="car")
    assert ranked[0]["routeId"] == "lake"
