from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _opening_range_time(value: dict[str, Any], timezone: ZoneInfo) -> datetime | None:
    try:
        date = datetime.fromisoformat(str(value["date"])).date()
        local = datetime.combine(date, time(int(value["hour"]), int(value["minute"])), tzinfo=timezone)
    except (KeyError, TypeError, ValueError):
        return None
    return local


def opening_state(poi: dict[str, Any], passing_time: datetime | None) -> str:
    if passing_time is None:
        return "UNKNOWN"
    poi_details = poi.get("poi", {})
    opening_hours = poi.get("openingHours") or poi.get("opening_hours") or (poi_details.get("openingHours") if isinstance(poi_details, dict) else None) or {}
    if isinstance(opening_hours, dict):
        poi_timezone = "Asia/Kolkata"
        time_zone_data = poi_details.get("timeZone", {}) if isinstance(poi_details, dict) else {}
        if isinstance(time_zone_data, dict):
            poi_timezone = time_zone_data.get("ianaId") or poi_timezone
        try:
            zone = ZoneInfo(poi_timezone)
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("Asia/Kolkata")
        current = passing_time.astimezone(zone) if passing_time.tzinfo else passing_time.replace(tzinfo=zone)
        for interval in opening_hours.get("timeRanges", []):
            start_at = _opening_range_time(interval.get("startTime", {}), zone)
            end_at = _opening_range_time(interval.get("endTime", {}), zone)
            if start_at is None or end_at is None:
                continue
            if start_at <= current < end_at:
                return "OPEN"
        ranges = opening_hours.get("timeRanges")
        if isinstance(ranges, list) and ranges:
            range_starts = [_opening_range_time(item.get("startTime", {}), zone) for item in ranges]
            range_ends = [_opening_range_time(item.get("endTime", {}), zone) for item in ranges]
            valid_starts = [item for item in range_starts if item is not None]
            valid_ends = [item for item in range_ends if item is not None]
            if not valid_starts or not valid_ends:
                return "UNKNOWN"
            fetched_at = poi.get("_safeRouteOpeningHoursFetchedAt")
            try:
                fetched = datetime.fromisoformat(fetched_at) if isinstance(fetched_at, str) else fetched_at
                if not isinstance(fetched, datetime):
                    fetched = min(valid_starts)
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=dt_timezone.utc)
                coverage_start = fetched.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
            except (TypeError, ValueError):
                coverage_start = min(valid_starts).replace(hour=0, minute=0, second=0, microsecond=0)
            coverage_end = coverage_start + timedelta(days=7)
            if current < coverage_start or current >= coverage_end:
                return "UNKNOWN"
            return "CLOSED"
        # Some provider responses only expose current status, not a dated
        # schedule. Do not use that status for a different requested time.
        status = str(opening_hours.get("status", "")).upper()
        fetched_at = poi.get("_safeRouteOpeningHoursFetchedAt")
        if status in {"OPEN", "CLOSED"} and isinstance(fetched_at, str):
            try:
                fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                compare = passing_time
                if compare.tzinfo is None:
                    compare = compare.replace(tzinfo=zone)
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=dt_timezone.utc)
                if compare.astimezone(dt_timezone.utc).date() == fetched.astimezone(dt_timezone.utc).date() and compare.hour == fetched.astimezone(zone).hour:
                    return status
            except ValueError:
                pass
    if isinstance(opening_hours, str):
        normalized = opening_hours.lower()
        if "24/7" in normalized or "open 24" in normalized:
            return "OPEN"
        try:
            opening, closing = normalized.split("-")[:2]
            start = time.fromisoformat(opening.strip())
            end = time.fromisoformat(closing.strip())
            current = passing_time.time()
            open_now = start <= current < end if start <= end else current >= start or current < end
            return "OPEN" if open_now else "CLOSED"
        except (ValueError, TypeError):
            pass
    return "UNKNOWN"
