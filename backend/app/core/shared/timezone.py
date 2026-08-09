from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.constants import MOSCOW_TZ


class SystemClock:
    """Encapsulates datetime logic adapted to system's utc_delta to make correct timezone unaware time"""

    def __init__(self, utc_delta: int) -> None:
        self._delta = timedelta(hours=utc_delta)

    def now(self) -> datetime:
        return (datetime.now(UTC) + self._delta).replace(tzinfo=None)


def get_current_datetime_with_moscow_tz() -> datetime:
    return datetime.now(tz=MOSCOW_TZ)


def convert_to_moscow_datetime(dt: datetime) -> datetime:
    return dt.replace(tzinfo=MOSCOW_TZ) if dt.tzinfo is None else dt.astimezone(MOSCOW_TZ)


def to_naive_moscow_datetime(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt

    moscow_dt = dt.astimezone(MOSCOW_TZ)
    return moscow_dt.replace(tzinfo=None, microsecond=0)


def _calculate_utc_offset_label(datetime_value: datetime) -> str:
    timezone_info = datetime_value.tzinfo
    if timezone_info is None:
        return "UTC"

    utc_offset_value = datetime_value.utcoffset()
    if utc_offset_value is None:
        return "UTC"

    total_offset_minutes = int(utc_offset_value.total_seconds() // 60)
    offset_sign = "+" if total_offset_minutes >= 0 else "-"
    absolute_offset_minutes = abs(total_offset_minutes)
    offset_hours = absolute_offset_minutes // 60
    offset_minutes = absolute_offset_minutes % 60

    return f"UTC{offset_sign}{offset_hours:02d}:{offset_minutes:02d}"


def _parse_datetime_from_iso_string(datetime_iso_string: str) -> datetime | None:
    normalized_datetime_iso_string = datetime_iso_string.strip()
    if not normalized_datetime_iso_string:
        return None

    if normalized_datetime_iso_string.endswith("Z"):
        normalized_datetime_iso_string = f"{normalized_datetime_iso_string[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized_datetime_iso_string)
    except ValueError:
        return None


def normalize_datetime_value(datetime_source_value: Any | None) -> datetime | None:
    if isinstance(datetime_source_value, datetime):
        return datetime_source_value

    if isinstance(datetime_source_value, str):
        return _parse_datetime_from_iso_string(datetime_source_value)

    return None


def format_datetime_for_human_readable_message(datetime_source_value: Any) -> str:
    normalized_datetime_value = normalize_datetime_value(datetime_source_value)
    if normalized_datetime_value is None:
        return "" if datetime_source_value is None else str(datetime_source_value)

    utc_offset_label = _calculate_utc_offset_label(normalized_datetime_value)
    return f"{normalized_datetime_value:%d.%m.%Y %H:%M} ({utc_offset_label})"
