"""Natural-language reminder times ("tomorrow at 5pm", "in 2 hours", "Monday morning") in the user's timezone."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser

_DAY_PARTS = {"morning": "9am", "afternoon": "2pm", "evening": "6pm", "night": "9pm"}
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
# Words that pin a date; without them "6pm" means the next 6pm, which may be today
_DATE_WORDS = re.compile(
    rf"\b(today|tonight|tomorrow|day after|{_WEEKDAYS}|week|month|year|in \d+|\d{{4}}-\d{{2}}-\d{{2}}|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}/\d{1,2})",
    re.IGNORECASE,
)


def resolve_timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _normalise(text: str) -> str:
    """Rewrite phrasings dateparser misses or misreads."""
    t = text.lower().strip()
    t = re.sub(r"\btonight\b", "today 8pm", t)
    t = re.sub(r"\bthis (morning|afternoon|evening)\b", lambda m: "today " + _DAY_PARTS[m.group(1)], t)
    t = re.sub(r"\b(morning|afternoon|evening|night)\b", lambda m: _DAY_PARTS[m.group(1)], t)
    t = re.sub(rf"\bnext ({_WEEKDAYS})\b", r"\1", t)
    # A bare "at 6" almost always means the afternoon/evening for 1-7, and that hour on the dot otherwise
    t = re.sub(
        r"\bat (\d{1,2})(?![\d:]|\s*(?:am|pm))",
        lambda m: f"at {m.group(1)}pm" if 1 <= int(m.group(1)) <= 7 else f"at {m.group(1)}:00",
        t,
    )
    return t


def parse_when(text: str, timezone: str | None = None, now: datetime | None = None) -> datetime | None:
    """Parse a reminder time to an aware UTC datetime, or None if it can't be understood.

    ISO timestamps (what the LLM passes) and natural language (what people type) both work. Times are
    interpreted in the user's timezone; ambiguous phrases resolve to the next matching moment.
    """
    tz = resolve_timezone(timezone)
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    phrase = _normalise(text)
    parsed = dateparser.parse(
        phrase,
        settings={
            "TIMEZONE": str(tz),
            "TO_TIMEZONE": str(tz),
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": now_local.replace(tzinfo=None),
        },
    )
    if parsed is None:
        return None
    # dateparser sometimes jumps a time-only phrase to tomorrow even when today's slot is still ahead
    if not _DATE_WORDS.search(phrase) and parsed - timedelta(days=1) > now_local:
        parsed -= timedelta(days=1)
    return parsed.astimezone(UTC)
