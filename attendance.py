"""Ishga kelish («доброе утро»), kech qolish jarimasi, kelmaganlarga eslatma va tanaffus (атайду / тут).

Matn faqat «Проёб» guruhida va faqat kalit so'zlarni topish uchun ko'riladi; saqlanmaydi.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from . import people as P
from .db import Database
from .timeutil import at, day_start, local_date, minutes_up, parse_hhmm

log = logging.getLogger("attendance")

_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                ["a", "b", "v", "g", "d", "e", "e", "j", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                 "u", "f", "h", "c", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya"]))


def norm(text: str) -> str:
    """Kirill va lotin (har xil yozilish) -> bitta lotin «asos»."""
    t = (text or "").lower().replace("ё", "е")
    t = "".join(_CYR.get(ch, ch) for ch in t)
    t = t.replace("y", "i").replace("w", "v").replace("q", "k")
    return re.sub(r"(.)\1+", r"\1", t)


_BREAK_START = re.compile(r"(?<![a-z])(ataid[uoa]?|pereriv|obed)(?![a-z])")
_BACK = {norm(w) for w in ("tut", "tutman", "qaytdim", "keldim", "вернулся", "vernulsya")}


def detect_break(text: str | None) -> str | None:
    """'start' | 'end' | None."""
    if not text:
        return None
    t = norm(text)
    if _BREAK_START.search(t):
        return "start"
    words = re.findall(r"[a-z]+", t)
    if 0 < len(words) <= 2 and any(w in _BACK for w in words):
        return "end"
    return None


def is_good_morning(text: str | None) -> bool:
    """«доброе утро», «Доброе утро!», «dobroe utro», «доброго утра», «добрый утро»…"""
    if not text or len(text) > 80:
        return False
    words = re.findall(r"[a-z]+", norm(text))
    return any(w.startswith("dobr") for w in words) and any(w.startswith("utr") for w in words)


def parse_late_fine(spec: str | None):
    """«0.5» → ('rate', 0.5) · «10=2, 30=5» → ('tiers', [(10, 2.0), (30, 5.0)]) · bo'sh/0 → None. Xato → ValueError."""
    t = (spec or "").strip().replace(",", " ").replace(";", " ")
    if not t or t in ("0", "-"):
        return None
    if "=" in t:
        tiers = []
        for a, b in re.findall(r"(\d+)\s*=\s*(\d+(?:[.]\d+)?)", t):
            tiers.append((int(a), float(b)))
        if not tiers or len(tiers) != t.count("="):
            raise ValueError("tiers")
        return "tiers", sorted(tiers)
    v = float(t)
    if v < 0:
        raise ValueError("neg")
    return ("rate", v) if v > 0 else None


def late_fine_amount(spec: str | None, late_min: int) -> float:
    try:
        rule = parse_late_fine(spec)
    except ValueError:
        return 0.0
    if rule is None or late_min <= 0:
        return 0.0
    kind, val = rule
    if kind == "rate":
        return round(late_min * val, 2)
    amount = 0.0
    for m, usd in val:
        if late_min >= m:
            amount = usd
    return amount


def late_fine_text(spec: str | None, lang: str = "uz") -> str:
    try:
        rule = parse_late_fine(spec)
    except ValueError:
        rule = None
    if rule is None:
        return "jarimasiz" if lang != "ru" else "без штрафа"
    kind, val = rule
    if kind == "rate":
        return f"{val:g} $ / daq" if lang != "ru" else f"{val:g} $ / мин"
    w = "daq" if lang != "ru" else "мин"
    return ", ".join(f"{m}+ {w} → {usd:g} $" for m, usd in val)


class Attendance:
    def __init__(self, db: Database, tz: ZoneInfo, notifier, clock=time.time):
        self.db = db
        self.tz = tz
        self.notifier = notifier
        self.clock = clock

    # ------------------------------------------------------------ sozlamalar
    def work_start(self):
        try:
            return parse_hhmm(self.db.get("work_start"))
        except ValueError:
            return parse_hhmm("10:00")

    @property
    def break_len(self) -> int:
        return max(1, self.db.get_int("break_minutes", 30)) * 60

    @property
    def breaks_per_day(self) -> int:
        return max(1, self.db.get_int("breaks_per_day", 3))

    def staff(self):
        """Ishga kelishi nazorat qilinadigan xodimlar: faol, «ish vaqti nazorati» yoqilgan, kamida bitta papkada."""
        return self.db.all("SELECT DISTINCT p.* FROM people p JOIN folder_people fp ON fp.person_id=p.id "
                           "WHERE p.active=1 AND p.attend=1 ORDER BY lower(p.name)")

    # ------------------------------------------------------------ guruhdagi xabar
    async def on_text(self, person, text: str, ts: int) -> str | None:
        """Guruhdagi xodim xabari. -> 'arrived' | 'late' | 'already' | 'break_*' | None."""
        if person is None:
            return None
        if self.db.flag("attendance_enabled") and is_good_morning(text):
            return self.arrive(person, ts)
        kind = detect_break(text)
        if kind and self.db.flag("breaks_enabled"):
            return self._break(person, kind, ts)
        return None

    def arrive(self, person, ts: int) -> str:
        day = local_date(ts, self.tz)
        row = self.db.one("SELECT * FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), person["id"]))
        if row is not None and row["arrived_ts"]:
            return "already"
        start = at(day, self.work_start(), self.tz)
        late = minutes_up(ts - start) if ts > start + 59 else 0
        if P.is_day_off(person, day.weekday()):
            late = 0
        self.db.run("INSERT INTO attendance(day, person_id, arrived_ts, late_min) VALUES(?,?,?,?) "
                    "ON CONFLICT(day, person_id) DO UPDATE SET arrived_ts=excluded.arrived_ts, late_min=excluded.late_min",
                    (day.isoformat(), person["id"], ts, late))
        amount = late_fine_amount(self.db.get("late_fine"), late)
        if late and amount > 0 and self.db.flag("fines_enabled"):
            from .kassa import add_adj
            add_adj(self.db, person["id"], "fine", amount, day.isoformat(), source="late",
                    note=f"опоздание {late} мин")
        return "late" if late else "arrived"

    # ------------------------------------------------------------ tanaffus
    def _break(self, person, kind: str, ts: int) -> str:
        cur = self.db.one("SELECT * FROM breaks WHERE person_id=? AND end_ts IS NULL ORDER BY id DESC LIMIT 1",
                          (person["id"],))
        if kind == "start":
            if cur is not None:
                if ts < cur["start_ts"] + self.break_len:
                    return "break_already"
                self.db.run("UPDATE breaks SET end_ts=? WHERE id=?", (cur["start_ts"] + self.break_len, cur["id"]))
            since = day_start(ts, self.tz)
            n = self.db.scalar("SELECT COUNT(*) FROM breaks WHERE person_id=? AND start_ts>=?", (person["id"], since))
            if n >= self.breaks_per_day:
                return "break_limit"
            self.db.run("INSERT INTO breaks(person_id, start_ts) VALUES(?,?)", (person["id"], ts))
            self.recompute_pauses(ts)
            return "break_start"
        if cur is None:
            return None
        self.db.run("UPDATE breaks SET end_ts=? WHERE id=?", (ts, cur["id"]))
        self.recompute_pauses(ts)
        return "break_end_late" if ts > cur["start_ts"] + self.break_len else "break_end"

    def _eff_end(self, br) -> int:
        limit = br["start_ts"] + self.break_len
        return min(br["end_ts"], limit) if br["end_ts"] is not None else limit

    def recompute_pauses(self, now: int) -> None:
        """Papka pauzada (zaderjka hisoblanmaydi), faqat uning HAMMA xodimi tanaffusda bo'lsa."""
        recent = self.db.all("SELECT * FROM breaks WHERE start_ts>=?", (now - 2 * 86400,))
        for f in P.folders(self.db):
            members = P.folder_people(self.db, f["id"])
            open_p = self.db.one("SELECT * FROM pauses WHERE folder_id=? AND end_ts IS NULL", (f["id"],))
            current, latest = [], []
            for m in members:
                mine = sorted([b for b in recent if b["person_id"] == m["id"] and b["start_ts"] <= now],
                              key=lambda b: b["start_ts"])
                last = mine[-1] if mine else None
                latest.append(last)
                current.append(last if last is not None and now < self._eff_end(last) else None)
            should = bool(members) and all(c is not None for c in current)
            if should and open_p is None:
                self.db.run("INSERT INTO pauses(folder_id, start_ts) VALUES(?,?)",
                            (f["id"], min(now, max(c["start_ts"] for c in current))))
            elif not should and open_p is not None:
                ends = [self._eff_end(b) for b in latest if b is not None]
                end_ts = min([now] + ends) if ends else now
                self.db.run("UPDATE pauses SET end_ts=? WHERE id=?", (max(end_ts, open_p["start_ts"]), open_p["id"]))

    # ------------------------------------------------------------ taymer
    async def tick(self, now: int | None = None) -> None:
        now = int(self.clock() if now is None else now)
        if not self.db.flag("bot_enabled"):
            return
        self.recompute_pauses(now)
        if self.db.flag("breaks_enabled"):
            await self._break_reminders(now)
        if self.db.flag("attendance_enabled"):
            await self._noshow(now)

    async def _break_reminders(self, now: int) -> None:
        for br in self.db.all("SELECT * FROM breaks WHERE end_ts IS NULL AND reminded=0"):
            due = br["start_ts"] + self.break_len
            if now < due:
                continue
            p = P.person(self.db, br["person_id"])
            try:
                await self.notifier.send_group(f"{P.mention(p)}, время перерыва вышло!")
                self.db.run("UPDATE breaks SET reminded=1 WHERE id=?", (br["id"],))
            except Exception as exc:
                log.warning("Tanaffus eslatmasi yuborilmadi: %s", exc)
                if now - due > 600:
                    self.db.run("UPDATE breaks SET reminded=1 WHERE id=?", (br["id"],))

    async def _noshow(self, now: int) -> None:
        day = local_date(now, self.tz)
        due = at(day, self.work_start(), self.tz) + max(1, self.db.get_int("noshow_minutes", 15)) * 60
        if now < due or now > due + 6 * 3600:
            return
        missing = []
        for p in self.staff():
            if P.is_day_off(p, day.weekday()):
                continue
            row = self.db.one("SELECT * FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), p["id"]))
            if row is not None and (row["arrived_ts"] or row["reminded"]):
                continue
            missing.append(p)
        if not missing:
            return
        text = " ".join(P.mention(p) for p in missing) + " — ещё нет «доброе утро»"
        try:
            await self.notifier.send_group(text)
        except Exception as exc:
            log.warning("Kelmaganlar eslatmasi yuborilmadi: %s", exc)
            return
        for p in missing:
            self.db.run("INSERT INTO attendance(day, person_id, reminded) VALUES(?,?,1) "
                        "ON CONFLICT(day, person_id) DO UPDATE SET reminded=1", (day.isoformat(), p["id"]))

    # ------------------------------------------------------------ hisobot uchun
    def day_summary(self, day) -> list[dict]:
        out = []
        for p in self.staff():
            row = self.db.one("SELECT * FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), p["id"]))
            off = P.is_day_off(p, day.weekday())
            out.append({"p": p, "off": off, "arrived": row["arrived_ts"] if row else None,
                        "late": row["late_min"] if row else 0})
        return out


def week_days(d) -> list:
    mon = d - timedelta(days=d.weekday())
    return [mon + timedelta(days=i) for i in range(7)]
