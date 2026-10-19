"""Vaqt: ish vaqti, sutka chegaralari, sanalar va kiritilgan matnni tushunish."""
from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_HHMM = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*$")


def parse_hhmm(value: str) -> time:
    """'10:00', '10.00', '9:30', '10' -> time. Xato bo'lsa ValueError."""
    m = _HHMM.match(value or "")
    if not m:
        raise ValueError("time")
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if hour > 23 or minute > 59:
        raise ValueError("time")
    return time(hour, minute)


def hhmm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def work_seconds(start_ts: float, end_ts: float, tz: ZoneInfo, ws: time, we: time) -> int:
    """[start, end] oralig'idan ish vaqtiga (ws–we) to'g'ri keladigan soniyalar."""
    if end_ts <= start_ts:
        return 0
    start_ts = max(start_ts, end_ts - 400 * 86400)
    start, end = datetime.fromtimestamp(start_ts, tz), datetime.fromtimestamp(end_ts, tz)
    total, day = 0.0, start.date()
    while day <= end.date():
        lo = max(datetime.combine(day, ws, tzinfo=tz), start)
        hi = min(datetime.combine(day, we, tzinfo=tz), end)
        if hi > lo:
            total += (hi - lo).total_seconds()
        day += timedelta(days=1)
    return int(total)


def is_work_time(ts: float, tz: ZoneInfo, ws: time, we: time) -> bool:
    return ws <= datetime.fromtimestamp(ts, tz).time().replace(tzinfo=None) < we


def day_start(ts: float, tz: ZoneInfo) -> int:
    d = datetime.fromtimestamp(ts, tz).date()
    return int(datetime.combine(d, time(0, 0), tzinfo=tz).timestamp())


def local_date(ts: float, tz: ZoneInfo) -> date:
    return datetime.fromtimestamp(ts, tz).date()


def at(d: date, t: time, tz: ZoneInfo) -> int:
    return int(datetime.combine(d, t, tzinfo=tz).timestamp())


def fmt(ts: float, tz: ZoneInfo, pattern: str = "%d.%m %H:%M") -> str:
    return datetime.fromtimestamp(ts, tz).strftime(pattern)


def minutes_up(seconds: float) -> int:
    """Soniyalarni daqiqaga yuqoriga yaxlitlash (61 s = 2 daq)."""
    return int(math.ceil(max(0.0, seconds) / 60.0))


def parse_date(value: str, ref: date | None = None) -> date:
    """'2026-08-26', '26.08.2026', '26.08' -> date. Xato bo'lsa ValueError."""
    v = (value or "").strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(v, pattern).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})", v)
    if m:
        ref = ref or date.today()
        d = date(ref.year, int(m.group(2)), int(m.group(1)))
        if d > ref + timedelta(days=45):
            d = d.replace(year=ref.year - 1)
        return d
    raise ValueError("date")


def parse_minutes(value: str) -> int:
    """'30' / '30 daq' / '30м' -> 30; '2 soat' / '2ч' -> 120; '1 kun' -> 1440; '0' / "o'ch" / 'выкл' -> 0."""
    v = (value or "").strip().lower().replace(",", ".")
    for ch in "ʻʼ‘’`":
        v = v.replace(ch, "'")
    if v in ("", "0", "выкл", "off", "нет", "o'ch", "och", "yo'q", "yoq"):
        return 0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-zа-я]*)", v)
    if not m:
        raise ValueError("minutes")
    num, unit = float(m.group(1)), m.group(2)
    if unit in ("", "m", "min", "м", "мин", "daq", "daqiqa"):
        mult = 1
    elif unit in ("h", "ч", "час", "часа", "часов", "soat"):
        mult = 60
    elif unit in ("d", "д", "дн", "день", "дня", "дней", "kun"):
        mult = 1440
    else:
        raise ValueError("unit")
    return int(round(num * mult))


def parse_number(value: str) -> float | None:
    try:
        return float((value or "").strip().replace(" ", "").replace(",", ".").replace("$", "").replace("%", ""))
    except ValueError:
        return None
