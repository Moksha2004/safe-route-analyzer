from datetime import datetime

from app.scoring.activity import opening_state


def test_opening_state_unknown_is_not_closed():
    assert opening_state({}, datetime(2026, 10, 25, 21, 0)) == "UNKNOWN"


def test_opening_state_parses_simple_overnight_interval():
    poi = {"openingHours": "20:00-02:00"}
    assert opening_state(poi, datetime(2026, 10, 25, 23, 0)) == "OPEN"
    assert opening_state(poi, datetime(2026, 10, 25, 12, 0)) == "CLOSED"


def test_opening_state_reads_tomtom_nested_time_ranges():
    poi = {"poi": {"openingHours": {"timeRanges": [{"startTime": {"date": "2026-10-25", "hour": 20, "minute": 0}, "endTime": {"date": "2026-10-25", "hour": 23, "minute": 0}}]}}}
    assert opening_state(poi, datetime(2026, 10, 25, 21, 0)) == "OPEN"


def test_opening_state_uses_selected_weekday_date_not_just_clock_time():
    poi = {"poi": {"openingHours": {"timeRanges": [
        {"startTime": {"date": "2026-10-26", "hour": 9, "minute": 0}, "endTime": {"date": "2026-10-26", "hour": 17, "minute": 0}},
    ]}}}
    assert opening_state(poi, datetime(2026, 10, 26, 10, 0)) == "OPEN"
    assert opening_state(poi, datetime(2026, 10, 27, 10, 0)) == "CLOSED"


def test_opening_state_returns_unknown_outside_tomtom_weekly_window():
    poi = {"poi": {"openingHours": {"timeRanges": [
        {"startTime": {"date": "2026-10-26", "hour": 9, "minute": 0}, "endTime": {"date": "2026-10-26", "hour": 17, "minute": 0}},
    ]}}}
    assert opening_state(poi, datetime(2026, 10, 20, 10, 0)) == "UNKNOWN"


def test_opening_state_converts_passing_time_to_poi_timezone():
    poi = {
        "_safeRouteOpeningHoursFetchedAt": "2026-10-25T00:00:00+00:00",
        "poi": {
            "timeZone": {"ianaId": "Asia/Kolkata"},
            "openingHours": {"timeRanges": [
                {"startTime": {"date": "2026-10-25", "hour": 9, "minute": 0}, "endTime": {"date": "2026-10-25", "hour": 17, "minute": 0}},
            ]},
        },
    }
    # 09:00 IST is 03:30 UTC on the same calendar day.
    assert opening_state(poi, datetime.fromisoformat("2026-10-25T03:30:00+00:00")) == "OPEN"
