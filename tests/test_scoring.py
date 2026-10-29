from app.scoring.night_activity import score_night_activity
from app.scoring.ranking import rank_routes
from app.scoring.street_lighting import normalize_lamp_density
from app.scoring.weights import is_night_hour


def test_lighting_score_is_relative_to_alternatives():
    density = normalize_lamp_density([0, 4, 8], [1000, 1000, 1000])
    assert density == [(0.0, 0.0), (4.0, 50.0), (8.0, 100.0)]


def test_similar_lamp_densities_get_similar_lighting_scores():
    density = normalize_lamp_density([16, 13], [10_000, 10_000])
    assert density == [(1.6, 100.0), (1.3, 81.2)]


def test_empty_lighting_is_zero():
    assert normalize_lamp_density([0, 0], [1000, 2000]) == [(0.0, 0.0), (0.0, 0.0)]


def test_night_score_includes_lighting_and_treats_missing_signals_as_neutral():
    score, breakdown = score_night_activity({"streetLighting": 100, "policePresence": 50})
    assert score == 61.0
    assert breakdown["components"]["streetLighting"] == 100
    assert breakdown["evidenceCoverage"] == 44.0
    assert "nightTrafficActivity" in breakdown["missingSignals"]


def test_single_strong_signal_cannot_produce_a_perfect_score():
    score, breakdown = score_night_activity({"policePresence": 100})
    assert score == 61.0
    assert breakdown["evidenceCoverage"] == 22.0


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
