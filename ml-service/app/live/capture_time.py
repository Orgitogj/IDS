from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.live import protocol

CAPTURE_COLUMNS = ["timestamp", "Timestamp", "flow_start", "Flow Start"]

CAPTURE_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S.%f",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
]


class UnknownCaptureTimezone(ValueError):
    pass


def _zone(timezone_name):
    if not timezone_name:
        return None
    try:
        return ZoneInfo(str(timezone_name))
    except (ZoneInfoNotFoundError, ValueError, KeyError) as error:
        raise UnknownCaptureTimezone(
            f"zona kohore e kapjes s'njihet: {timezone_name}") from error


def _as_utc(moment, assume_utc, zone=None):
    if moment.tzinfo is None:
        if zone is not None:
            moment = moment.replace(tzinfo=zone)
        elif assume_utc:
            moment = moment.replace(tzinfo=timezone.utc)
        else:
            return None
    return moment.astimezone(timezone.utc)


def parse(value, assume_utc=True, timezone_name=None):
    zone = _zone(timezone_name)

    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value, assume_utc, zone)

    text = str(value).strip()
    if not text:
        return None

    try:
        return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")),
                       assume_utc, zone)
    except ValueError:
        pass

    for fmt in CAPTURE_FORMATS:
        try:
            return _as_utc(datetime.strptime(text, fmt), assume_utc, zone)
        except ValueError:
            continue

    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def resolve(row, fallback=None, assume_utc=True, timezone_name=None):
    _zone(timezone_name)
    for column in CAPTURE_COLUMNS:
        if column not in row:
            continue
        moment = parse(row[column], assume_utc=assume_utc,
                       timezone_name=timezone_name)
        if moment is not None:
            return {
                "capture_timestamp": moment.isoformat().replace("+00:00", "Z"),
                "capture_timestamp_source": protocol.CAPTURE_TIME_EXACT,
                "capture_timestamp_column": column,
                "capture_timestamp_is_approximate": False,
                "capture_timestamp_assumed_utc": bool(assume_utc and not timezone_name),
                "capture_timestamp_timezone": (str(timezone_name) if timezone_name
                                               else "UTC"),
            }

    moment = fallback or datetime.now(timezone.utc)
    return {
        "capture_timestamp": moment.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"),
        "capture_timestamp_source": protocol.CAPTURE_TIME_APPROX_INGEST,
        "capture_timestamp_column": None,
        "capture_timestamp_is_approximate": True,
        "capture_timestamp_assumed_utc": True,
        "capture_timestamp_timezone": "UTC",
        "capture_timestamp_note": (
            "No usable capture column was present, so the agent read time is recorded as a "
            "clearly named approximation. It is not a packet-capture time and must not be "
            "presented as one."),
    }
