"""Ishga kelish, kech qolish, kelmaganlarga eslatma va tanaffus (egasi bilan kelishilgan, 2026-10-30).

* Ishga keldi = «Проёб»ga birinchi xabari (kechki kassa hisobotidan tashqari) yoki lidga birinchi yozuvi.
* Kech qolish — ish boshlanishidan N daqiqa (late_after_min, 15) va undan ko'p kech kelsa: «Проёб»da
  «🕘 @baxa, вы опоздали на 40 мин — вам штраф 15 $ (2-е опоздание за неделю)». Kamiga — xabar ham, jarima ham yo'q.
  Summa — necha daqiqa kech qolganiga qarab (💸 jadval: 30 daq → 10 $, 40 → 15 $, 1 soat → 25 $, 2 soat → 50 $).
* Tanaffus so'zlari har xil yoziladi: отойду / отойди / атайду / otaydu / ataydim / перерыв / tanaffus / obedga /
  perekur / namozga … va egasi qo'shgan so'zlar. Bot javob beradi: «☕ @baxa — перерыв до 14:30».
* Tanaffus vaqtida lidga yozsa — tanaffus tugamaydi (nozik mijozga yozib qo'yishi mumkin). Vaqti tugagach lidga yozsa
  yoki «Проёб»ga yozsa — qaytdi. «тут» / «keldim» — istalgan payt qaytdi. Vaqt tugab jim bo'lsa — eslatma.
* Kim ishlaydi — 📅 «Bugun kim qayerda» bo'yicha (dam olayotgan belgilanmaydi va kech qolmaydi).

Matn faqat «Проёб» guruhida va faqat kalit so'zlarni topish uchun ko'riladi; saqlanmaydi.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from . import people as P
from . import roster as R
from .db import Database
from .timeutil import at, day_start, local_date, minutes_up, parse_hhmm

log = logging.getLogger("attendance")

_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                ["a", "b", "v", "g", "d", "e", "e", "j", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                 "u", "f", "h", "c", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya"]))
_UZ = str.maketrans({"ў": "o", "қ": "k", "ғ": "g", "ҳ": "h", "ʻ": "", "ʼ": "", "'": "", "‘": "", "’": "", "`": ""})


def norm(text: str) -> str:
    """Kirill va lotin (har xil yozilish) -> bitta lotin «asos»."""
    t = (text or "").lower().replace("ё", "е").translate(_UZ)
    t = "".join(_CYR.get(ch, ch) for ch in t)
    t = t.replace("y", "i").replace("w", "v").replace("q", "k").replace("x", "h")
    return re.sub(r"(.)\1+", r"\1", t)


def fold(text: str) -> str:
    """Tanaffus so'zlari uchun: «o» va «a» farqi yo'q (отойду = атайду = otaydu = ataydim)."""
    return re.sub(r"(.)\1+", r"\1", norm(text).replace("o", "a"))


# tanaffus boshlanishi — so'z shu bilan boshlansa (yozilish farqi fold() bilan yo'qoladi)
_BREAK_SRC = ("отойд", "атайд", "otayd", "atoyd", "ataid", "отхож", "отош", "отлуч", "отбег", "перерыв", "перерв",
              "pererv", "перекур", "покур", "курит", "обед", "obet", "abet", "tanaf", "танаф", "namoz", "намаз",
              "намоз", "tushlik", "тушлик", "молитв")
BREAK_STEMS = tuple(sorted({fold(w) for w in _BREAK_SRC}))
_LUNCH = (fold("обед"), fold("abet"))
_GONE = fold("отош")
# qaytish — butun so'z
_BACK_SRC = ("тут", "tut", "tutman", "здесь", "zdes", "вернулся", "вернулась", "vernulsya", "vernulas", "пришел",
             "пришла", "prishel", "prishla", "qaytdim", "kaytdim", "keldim", "келдим", "keldik", "месте", "ishdaman",
             "joyidaman", "joyimdaman")
BACK_WORDS = frozenset(fold(w) for w in _BACK_SRC)
MAX_WORDS = 12                 # bundan uzun xabar — tanaffus e'loni emas (oddiy gap)
BREAK_GRACE = 180              # tanaffus vaqti tugagach shuncha soniya hech qayerga yozmasa (jim) — «Проёб»da eslatma
BREAK_ACTIVE = 300             # tanaffusning oxirgi 5 daqiqasida lidga yozgan — allaqachon ishlayapti, eslatma yo'q
BREAK_STALE = 3600             # bundan eski ochiq tanaffus (bot o'chib turgan) — eslatma kech, yuborilmaydi


def _words(raw: str | None) -> tuple[str, ...]:
    """Egasi qo'shgan so'zlar (vergul bilan): bitta so'z — so'z boshi bo'yicha, bir necha so'z — ibora bo'yicha."""
    out = []
    for x in re.split(r"[,;\n]+", raw or ""):
        w = " ".join(re.findall(r"[a-z]+", fold(x)))
        if len(w) >= 3:
            out.append(w)
    return tuple(out)


def _has(words: list[str], phrases: tuple) -> bool:
    """So'zlar ichida egasi qo'shgan so'z/ibora bormi."""
    line = " " + " ".join(words) + " "
    for ph in phrases:
        if " " in ph:
            if f" {ph}" in line:
                return True
        elif any(w.startswith(ph) for w in words):
            return True
    return False


def break_minutes(text: str | None) -> int | None:
    """«отойду на 30 минут» → 30, «перерыв 15м» → 15, «полчаса» → 30, «на час» → 60. Aytilmagan — None."""
    if not text:
        return None
    t = norm(text)
    if "polchas" in t or "iarim soat" in t:
        return 30
    hour = r"(?<![a-z])(chas|chasa|chasov|soat|soatga)(?![a-z])"
    m = re.search(r"(?<![\d:.])(\d{1,3})(?![\d:.])", t)
    if m:
        v = int(m.group(1))
        if re.search(r"\d{1,3}\s*" + hour, t):
            v *= 60
        return v if 1 <= v <= 240 else None
    if re.search(hour, t):
        return 60
    return None


def detect_break(text: str | None, extra_break: tuple = (), extra_back: tuple = ()) -> str | None:
    """'start' | 'end' | None. extra_* — egasi panelda qo'shgan so'zlar (so'z boshi bo'yicha)."""
    if not text or len(text) > 300:
        return None
    words = re.findall(r"[a-z]+", fold(text))
    if not words or len(words) > MAX_WORDS:
        return None
    if len(words) <= 6 and (any(w in BACK_WORDS for w in words) or _has(words, tuple(extra_back))):
        return "end"
    if text.rstrip().endswith("?"):                        # «кто на обед?» — savol, tanaffus emas
        return None
    for i, w in enumerate(words):
        for s in BREAK_STEMS:
            if not w.startswith(s):
                continue
            if s in _LUNCH and (w[len(s):].startswith(("dan", "an")) or (i and words[i - 1].startswith("pasl"))):
                continue                                   # «obeddan keyin», «после обеда» — tanaffus emas
            if s == _GONE and i and words[i - 1] not in ("ia", "men"):
                continue                                   # «клиент отошёл» — boshqa odam haqida, tanaffus emas
            return "start"
    if _has(words, tuple(extra_break)):
        return "start"
    return None


def is_good_morning(text: str | None) -> bool:
    """«доброе утро», «Доброе утро!», «dobroe utro», «доброго утра», «добрый утро»…"""
    if not text or len(text) > 80:
        return False
    words = re.findall(r"[a-z]+", norm(text))
    return any(w.startswith("dobr") for w in words) and any(w.startswith("utr") for w in words)


def late_after(db) -> int:
    """Shuncha daqiqa va undan ko'p kech kelsa — «kech qoldi»."""
    return max(1, db.get_int("late_after_min", 15))


# ───────────────────────── tanaffus (modul darajasida — zaderjka va jarima ham ishlatadi)
def break_len(db) -> int:
    return max(1, db.get_int("break_minutes", 30)) * 60


def length(db, br) -> int:
    """Shu tanaffusning vaqti (soniya): aytilgan bo'lsa — o'sha, lekin umumiy limitdan oshmaydi."""
    stated = br["minutes"] if "minutes" in br.keys() else None
    return min(break_len(db), stated * 60) if stated else break_len(db)


def open_break(db, pid: int):
    return db.one("SELECT * FROM breaks WHERE person_id=? AND end_ts IS NULL ORDER BY id DESC LIMIT 1", (pid,))


def break_until(db, pid: int, now: int) -> int | None:
    """Hozir tanaffusdami — tanaffus tugaydigan vaqt (yoki None)."""
    br = open_break(db, pid)
    if br is None or br["start_ts"] > now:
        return None
    end = br["start_ts"] + length(db, br)
    return end if now < end else None


class Attendance:
    def __init__(self, db: Database, tz: ZoneInfo, notifier, clock=time.time):
        self.db = db
        self.tz = tz
        self.notifier = notifier
        self.clock = clock
        self._work_ts: dict[int, int] = {}            # xodim -> oxirgi marta lidga yozgan vaqti (tanaffus eslatmasi uchun)

    # ------------------------------------------------------------ sozlamalar
    def work_start(self):
        try:
            return parse_hhmm(self.db.get("work_start"))
        except ValueError:
            return parse_hhmm("10:00")

    def work_end(self):
        try:
            return parse_hhmm(self.db.get("work_end"))
        except ValueError:
            return parse_hhmm("23:00")

    @property
    def break_len(self) -> int:
        return break_len(self.db)

    @property
    def breaks_per_day(self) -> int:
        return max(1, self.db.get_int("breaks_per_day", 3))

    def words(self) -> tuple[tuple, tuple]:
        return _words(self.db.get("break_words")), _words(self.db.get("back_words"))

    def staff(self, day=None):
        """Ishga kelishi nazorat qilinadigan xodimlar: faol, «ish vaqti nazorati» yoqilgan, shu kuni biror RD da
        ishlaydi (📅 Bugun kim qayerda)."""
        day = day or local_date(self.clock(), self.tz)
        return [p for p in self.tracked() if R.works(self.db, p, day)]

    def tracked(self):
        return self.db.all("SELECT DISTINCT p.* FROM people p WHERE p.active=1 AND p.attend=1 AND (EXISTS (SELECT 1 FROM "
                           "folder_people fp WHERE fp.person_id=p.id) OR EXISTS (SELECT 1 FROM roster r WHERE "
                           "r.person_id=p.id)) ORDER BY lower(p.name)")

    # ------------------------------------------------------------ guruhdagi xabar
    async def on_text(self, person, text: str, ts: int, report: bool = False) -> dict:
        """«Проёб»dagi xodim xabari. -> {"arrive": 'late'|'arrived'|'greeted'|'already',
        "break": 'break_start'|'break_already'|'break_limit'|'break_end'|'break_end_late'|'back_auto',
        "cmd": True — tanaffus/qaytish so'zi yoki «доброе утро» (kassa hisoboti emas)}.
        report=True — kassa hisoboti: ishga kelish hisoblanmaydi (kechki hisobot)."""
        ev: dict = {}
        if person is None:
            return ev
        kind = None
        greet = is_good_morning(text)
        if self.db.flag("breaks_enabled") and not report:
            extra_break, extra_back = self.words()
            kind = detect_break(text, extra_break, extra_back)
        if self.db.flag("attendance_enabled") and not report:
            res = self.arrive(person, ts, via="greet" if greet else "msg")
            if res:
                ev["arrive"] = res
        if kind == "start":
            ev["break"] = self._break(person, "start", ts, break_minutes(text))
        elif kind == "end":
            res = self._break(person, "end", ts)
            if res:
                ev["break"] = res
        elif self.db.flag("breaks_enabled") and self.back_if_over(person, ts):
            ev["break"] = "back_auto"
        ev["cmd"] = bool(kind) or greet
        return ev

    def _window(self, ts: int) -> bool:
        """Ishga kelish shu oraliqda sanaladi: ish boshlanishidan 2 soat oldin — ish tugaguncha."""
        day = local_date(ts, self.tz)
        return at(day, self.work_start(), self.tz) - 2 * 3600 <= ts < at(day, self.work_end(), self.tz)

    def arrive(self, person, ts: int, via: str = "greet") -> str | None:
        """Ishga keldi: «Проёб»ga birinchi xabari (via='greet'/'msg') yoki lidga birinchi yozuvi (via='work') — qaysi
        biri oldin bo'lsa. Kech qolish shu vaqtdan; late_after_min dan kam bo'lsa — kech emas."""
        if not self._window(ts):
            return None
        day = local_date(ts, self.tz)
        iso = day.isoformat()
        row = self.db.one("SELECT * FROM attendance WHERE day=? AND person_id=?", (iso, person["id"]))
        if via == "greet" and row is not None and row["greet_ts"] is None:
            self.db.run("UPDATE attendance SET greet_ts=? WHERE day=? AND person_id=?", (ts, iso, person["id"]))
        if row is not None and row["arrived_ts"]:
            return "greeted" if via == "greet" and row["greet_ts"] is None else "already"
        start = at(day, self.work_start(), self.tz)
        late = minutes_up(ts - start) if ts > start + 59 else 0
        if late < late_after(self.db) or not person["attend"] or not R.works(self.db, person, day):
            late = 0                                        # 15 daqiqadan kam yoki bugun ishlamaydi — kech emas
        self.db.run("INSERT INTO attendance(day, person_id, arrived_ts, late_min, greet_ts) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(day, person_id) DO UPDATE SET arrived_ts=excluded.arrived_ts, late_min=excluded.late_min, "
                    "greet_ts=COALESCE(attendance.greet_ts, excluded.greet_ts)",
                    (iso, person["id"], ts, late, ts if via == "greet" else None))
        self.db.run("UPDATE attendance SET last_act_ts=MAX(COALESCE(last_act_ts, 0), ?) WHERE day=? AND person_id=?",
                    (ts, iso, person["id"]))
        if not late:
            return "arrived"
        from . import fines
        fines.strike(self.db, person["id"], "late", day, ts, ref=f"late:{iso}", note=f"опоздание {late} мин",
                     minutes=late)                          # summa — necha daqiqa kech qolganiga qarab (jadval)
        return "late"

    def late_strike(self, person_id: int, day):
        return self.db.one("SELECT s.n, s.usd FROM strikes s LEFT JOIN adj a ON a.id=s.adj_id WHERE s.person_id=? "
                           "AND s.kind='late' AND s.day=? AND (s.adj_id IS NULL OR a.cancelled=0) ORDER BY s.id DESC "
                           "LIMIT 1", (person_id, day.isoformat() if hasattr(day, "isoformat") else str(day)))

    def late_fined(self, person_id: int, day) -> bool:
        """Kechikish uchun jarima yozilganmi — yozilgan bo'lsa, xabar «Проёб»da qoladi (o'chmaydi)."""
        s = self.late_strike(person_id, day)
        return s is not None and float(s["usd"] or 0) > 0

    def late_text(self, person, late_min: int, ts: int) -> str:
        """«Проёб» uchun, qisqa va muloyim (egasi):
        🕘 @baxa, вы опоздали на 25 мин — вам штраф 10 $ (2-е опоздание за неделю)
        начало в 10:25 · по графику 10:00            ← mayda"""
        from . import fines
        from .gtext import esc, small
        from .timeutil import fmt
        ws = self.work_start()
        hrs, mins = divmod(max(0, int(late_min or 0)), 60)
        dur = (f"{hrs} ч {mins:02d} мин" if mins else f"{hrs} ч") if hrs else f"{mins} мин"
        text = f"🕘 {esc(P.mention(person))}, вы опоздали на {dur}"
        s = self.late_strike(person["id"], local_date(ts, self.tz))
        if s is not None and self.db.flag("fines_enabled"):
            text += fines.late_tail({"n": s["n"], "usd": float(s["usd"] or 0)})
        return text + "\n" + small(f"начало в {fmt(ts, self.tz, '%H:%M')} · по графику {ws.hour:02d}:{ws.minute:02d}")

    async def work_seen(self, person, ts: int) -> str | None:
        """Xodim lidga yozdi: ishga kelgan (kech bo'lsa — «Проёб»da xabar) va tanaffus vaqti tugagan bo'lsa — qaytgan.
        Tanaffus vaqtida lidga yozsa — tanaffus davom etadi."""
        if not person["active"]:
            return None
        if ts > self._work_ts.get(person["id"], 0):
            self._work_ts[person["id"]] = ts
        if self.db.flag("breaks_enabled"):
            self.back_if_over(person, ts)
        if not self.db.flag("attendance_enabled") or not person["attend"]:
            return None
        day = local_date(ts, self.tz)
        if not self._window(ts):
            return None                                    # tungi yozishmalar — yangi kunga kelish emas
        self.db.run("UPDATE attendance SET last_act_ts=MAX(COALESCE(last_act_ts, 0), ?) WHERE day=? AND person_id=?",
                    (ts, day.isoformat(), person["id"]))   # oxirgi faollik
        row = self.db.one("SELECT arrived_ts FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), person["id"]))
        if row is not None and row["arrived_ts"]:
            return None
        if not R.works(self.db, person, day):
            return None
        res = self.arrive(person, ts, via="work")
        if res == "late":
            row = self.db.one("SELECT late_min FROM attendance WHERE day=? AND person_id=?",
                              (day.isoformat(), person["id"]))
            try:
                await self.notifier.send_group(self.late_text(person, row["late_min"] if row else 0, ts),
                                               trash=None if self.late_fined(person["id"], day) else "info")
            except Exception as exc:
                log.warning("Kech qolish xabari yuborilmadi: %s", exc)
        return res

    # ------------------------------------------------------------ tanaffus
    def length(self, br) -> int:
        return length(self.db, br)

    def break_end_ts(self, br) -> int:
        return br["start_ts"] + self.length(br)

    def back_if_over(self, person, ts: int) -> str | None:
        """Tanaffus vaqti tugagan, xodim yana yozdi (lidga yoki «Проёб»ga) — qaytdi."""
        cur = open_break(self.db, person["id"])
        if cur is None or ts < cur["start_ts"] + self.length(cur):
            return None
        self.db.run("UPDATE breaks SET end_ts=? WHERE id=?", (ts, cur["id"]))
        self.recompute_pauses(ts)
        return "break_end_late"

    def _break(self, person, kind: str, ts: int, minutes: int | None = None) -> str | None:
        cur = open_break(self.db, person["id"])
        if kind == "start":
            if cur is not None:
                if ts < cur["start_ts"] + self.length(cur):
                    return "break_already"
                self.db.run("UPDATE breaks SET end_ts=? WHERE id=?", (cur["start_ts"] + self.length(cur), cur["id"]))
            since = day_start(ts, self.tz)
            n = self.db.scalar("SELECT COUNT(*) FROM breaks WHERE person_id=? AND start_ts>=?", (person["id"], since))
            if n >= self.breaks_per_day:
                return "break_limit"
            self.db.run("INSERT INTO breaks(person_id, start_ts, minutes) VALUES(?,?,?)", (person["id"], ts, minutes))
            self.recompute_pauses(ts)
            return "break_start"
        if cur is None:
            return None
        self.db.run("UPDATE breaks SET end_ts=? WHERE id=?", (ts, cur["id"]))
        self.recompute_pauses(ts)
        return "break_end_late" if ts > cur["start_ts"] + self.length(cur) else "break_end"

    def break_text(self, person, ts: int) -> str:
        """«☕ @baxa — перерыв до 14:30» (javob sifatida)."""
        from .gtext import esc
        from .timeutil import fmt
        cur = open_break(self.db, person["id"])
        until = self.break_end_ts(cur) if cur is not None else ts + self.break_len
        return f"☕ {esc(P.mention(person))} — перерыв до {fmt(until, self.tz, '%H:%M')}"

    def _eff_end(self, br) -> int:
        limit = br["start_ts"] + self.length(br)
        return min(br["end_ts"], limit) if br["end_ts"] is not None else limit

    def recompute_pauses(self, now: int) -> None:
        """RD pauzada (zaderjka hisoblanmaydi), faqat uning bugungi HAMMA xodimi tanaffusda bo'lsa."""
        recent = self.db.all("SELECT * FROM breaks WHERE start_ts>=?", (now - 2 * 86400,))
        day = local_date(now, self.tz)
        for f in P.folders(self.db):
            members = R.workers(self.db, f["id"], day)
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
        """Tanaffus vaqti tugadi va xodim JIM (3 daqiqa lidga ham, «Проёб»ga ham yozmadi) — «Проёб»da eslatma.
        Vaqt tugagach birinchi yozgani (lidga yoki «Проёб»ga) — qaytdi, eslatma kerak emas. Tanaffusning oxirgi
        5 daqiqasida lidga yozib turgan bo'lsa — u allaqachon ishlayapti: eslatma yo'q."""
        for br in self.db.all("SELECT * FROM breaks WHERE end_ts IS NULL AND reminded=0"):
            due = br["start_ts"] + self.length(br)
            if now < due:
                continue
            p = P.person(self.db, br["person_id"])
            last = self._work_ts.get(br["person_id"], 0)
            if p is None or now - due > BREAK_STALE or (last > br["start_ts"] and last >= due - BREAK_ACTIVE):
                self.db.run("UPDATE breaks SET reminded=1 WHERE id=?", (br["id"],))
                continue
            if now < due + BREAK_GRACE:
                continue
            try:
                from .gtext import esc
                await self.notifier.send_group(f"☕ перерыв · {esc(P.mention(p))} — время перерыва вышло!", trash="info")
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
        missing = []                                       # bugun ishlaydi, lekin hali ko'rinmagan
        for p in self.staff(day):
            row = self.db.one("SELECT * FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), p["id"]))
            if row is not None and (row["greet_ts"] or row["reminded"] or row["arrived_ts"]):
                continue
            missing.append(p)
        if not missing:
            return
        from .gtext import mentions, small
        lines = [small("приход · напишите «доброе утро»"), f"{mentions(missing)} — ещё не видно в работе"]
        try:
            await self.notifier.send_group("\n".join(lines), trash="info")
        except Exception as exc:
            log.warning("Kelmaganlar eslatmasi yuborilmadi: %s", exc)
            return
        for p in missing:
            self.db.run("INSERT INTO attendance(day, person_id, reminded) VALUES(?,?,1) "
                        "ON CONFLICT(day, person_id) DO UPDATE SET reminded=1", (day.isoformat(), p["id"]))

    # ------------------------------------------------------------ hisobot uchun
    def day_summary(self, day) -> list[dict]:
        out = []
        for p in self.tracked():
            row = self.db.one("SELECT * FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), p["id"]))
            out.append({"p": p, "off": not R.works(self.db, p, day), "arrived": row["arrived_ts"] if row else None,
                        "late": row["late_min"] if row else 0})
        return out


def week_days(d) -> list:
    mon = d - timedelta(days=d.weekday())
    return [mon + timedelta(days=i) for i in range(7)]
