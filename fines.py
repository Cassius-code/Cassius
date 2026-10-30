"""💸 Jarimalar (egasi bilan kelishilgan, 2026-10-30).

* ⏰ zaderjka — «задержка» → eslatma → muhlat, shunda ham javob bo'lmasa — 1 ta. Bir vaqtda kechikkan lidlar va
  undan keyingi N daqiqa (fine_episode, 30) ichidagilari — o'sha 1 ta. Har KUNI noldan. Summa — zinapoya: 1-si, 2-si,
  3-si … egasi yozgan summalar bo'yicha («0 5 10 20»: oxirgisi keyingilarga ham). 0 — sanaladi, lekin pulsiz.
* 🕘 kech qolish — ish boshlanishidan N daqiqa (late_after_min, 15) va undan ko'p kech kelsa — 1 ta. Summa — necha
  daqiqa kech qolganiga qarab, egasi yozgan jadval bo'yicha («30-10, 40-15, 60-25, 2ч-50»: har summa o'sha daqiqadan
  boshlab, 35 daq → 10 $; birinchisidan kam — 0 $). Haftadagi nechanchisi (dushanbadan noldan) xabarda ko'rsatiladi.
Jarimalar o'chiq (yoki summalar yozilmagan) bo'lsa — hech narsa sanalmaydi va «штраф» so'zi chiqmaydi.
Jarima o'sha RD da shu kuni ishlayotgan xodimga (bitta RD — bitta xodim); tanaffusdagisiga — yo'q."""
from __future__ import annotations

import datetime as dt
import re

from . import people as P

KEYS = {"delay": "fine_ladder_delay"}
LATE_KEY = "fine_late_table"   # 🕘 kech qolish jadvali: «30=10 40=15 60=25 120=50» (daqiqa=$)
SOURCE = {"delay": "remind", "late": "late"}
MAX_STEPS = 10
MAX_LATE_MIN = 12 * 60


def parse_ladder(raw: str | None) -> list[float]:
    """«5 10 15 20» / «5, 10, 15» / «0 5 10» -> [5.0, 10.0, ...]. Bo'sh / yolg'iz «0» -> [] (o'chiq). Xato -> ValueError."""
    t = (raw or "").replace(",", " ").replace(";", " ").replace("$", " ").replace("→", " ").replace("-", " ").strip()
    if not t:
        return []
    vals = []
    for p in t.split():
        p = p.replace(",", ".")
        if not re.fullmatch(r"\d{1,4}(?:[.]\d{1,2})?", p):
            raise ValueError(p)
        vals.append(float(p))
    if len(vals) > MAX_STEPS:
        raise ValueError("too many")
    if len(vals) == 1 and vals[0] == 0:
        return []
    return vals


def ladder_raw(vals: list[float]) -> str:
    return " ".join(money(v) for v in vals)


def ladder(db, kind: str) -> list[float]:
    if kind not in KEYS:                          # kech qolish — zinapoya emas, daqiqa jadvali (late_table)
        return []
    try:
        return parse_ladder(db.get(KEYS[kind]))
    except ValueError:
        return []


# ───────────────────────── 🕘 kech qolish: necha daqiqa kech — necha $ (egasi yozadi, o'zgartiradi)
_HOURS = ("ч", "час", "часа", "часов", "soat", "s", "h")
_MINS = ("", "м", "мин", "минут", "m", "min", "daq", "daqiqa", "d")
_PAIR = re.compile(r"(\d+(?:[.,]\d+)?)\s*([^\W\d_]*)\.?\s*(?:[-=:→>–—]+|\s)\s*\$?\s*(\d+(?:[.,]\d+)?)\s*\$?")
_OFF = ("", "0", "-", "—", "yoq", "yo'q", "o'chiq", "ochiq", "выкл", "нет")


def parse_late_table(raw: str | None) -> list[tuple[int, float]]:
    """«30-10$ / 40-15 / 60-25 / 2ч-50$» (qatorlab yoki bir qatorda), «30=10 40=15», «1 soat - 25» ->
    [(30, 10.0), (40, 15.0), (60, 25.0), (120, 50.0)] (daqiqa bo'yicha tartibda). «0» / bo'sh -> [] (o'chiq).
    Xato (tushunarsiz qism, takror daqiqa, 10 tadan ko'p) -> ValueError."""
    t = (raw or "").strip().lower().replace("ʻ", "'").replace("’", "'")
    if t in _OFF:
        return []
    rows: dict[int, float] = {}
    left, pos = [], 0                              # juftlarga kirmagan qismlar (tushunarsiz narsa qolmasin)
    for m in _PAIR.finditer(t):
        left.append(t[pos:m.start()])
        pos = m.end()
        num, unit, usd = float(m.group(1).replace(",", ".")), m.group(2), float(m.group(3).replace(",", "."))
        if unit in _HOURS:
            minutes = int(round(num * 60))
        elif unit in _MINS:
            minutes = int(round(num))
        else:
            raise ValueError(unit)
        if not 1 <= minutes <= MAX_LATE_MIN or not 0 <= usd <= 1000 or minutes in rows:
            raise ValueError(m.group(0))
        rows[minutes] = round(usd, 2)
    rest = "".join(left) + t[pos:]
    if not rows or not re.fullmatch(r"[\s,;.$]*", rest) or len(rows) > MAX_STEPS:
        raise ValueError(rest.strip()[:20])
    return sorted(rows.items())


def late_table_raw(rows: list[tuple[int, float]]) -> str:
    """Bazada saqlash uchun: «30=10 40=15 60=25 120=50»."""
    return " ".join(f"{m}={money(v)}" for m, v in rows)


def late_table(db) -> list[tuple[int, float]]:
    try:
        return parse_late_table(db.get(LATE_KEY))
    except ValueError:
        return []


def late_amount(rows: list[tuple[int, float]], minutes: int) -> float:
    """Shuncha daqiqa kech qolganga summa: o'sha daqiqadan boshlab (35 daq, jadval 30-10 40-15 → 10 $)."""
    usd = 0.0
    for m, v in rows:
        if minutes >= m:
            usd = v
    return usd


def dur_text(minutes: int, lang: str = "uz") -> str:
    """30 → «30 daq», 60 → «1 soat», 90 → «1 s 30 daq» (ruscha: «30 мин», «1 ч», «1 ч 30 мин»)."""
    h, m = divmod(int(minutes), 60)
    if not h:
        return f"{m} мин" if lang == "ru" else f"{m} daq"
    if not m:
        return f"{h} ч" if lang == "ru" else f"{h} soat"
    return f"{h} ч {m} мин" if lang == "ru" else f"{h} s {m} daq"


def late_table_text(rows: list[tuple[int, float]], lang: str = "uz") -> str:
    """«30 daq → 10 $ · 40 daq → 15 $ · 1 soat → 25 $ · 2 soat → 50 $»."""
    if not rows:
        return "o'chiq" if lang != "ru" else "выкл"
    return " · ".join(f"{dur_text(m, lang)} → {money(v)} $" for m, v in rows)


def late_table_input(rows: list[tuple[int, float]]) -> str:
    """Egasi nusxa olib o'zgartirishi uchun, u yozgandek: «30-10 / 40-15 / 60-25 / 2ч-50» (qatorlab)."""
    return "\n".join((f"{m // 60}ч" if m % 60 == 0 and m >= 60 else str(m)) + f"-{money(v)}" for m, v in rows)


def on(db, kind: str) -> bool:
    if not db.flag("fines_enabled"):
        return False
    return bool(late_table(db)) if kind == "late" else bool(ladder(db, kind))


def money(v: float) -> str:
    v = round(float(v or 0), 2)
    return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:g}"


def ladder_text(lad: list[float], lang: str = "uz") -> str:
    """[0, 5, 10] -> «0 → 5 → 10 $»."""
    if not lad:
        return "o'chiq" if lang != "ru" else "выкл"
    return " → ".join(money(v) for v in lad) + " $"


def amount_for(lad: list[float], n: int) -> float:
    if not lad or n < 1:
        return 0.0
    return lad[min(n, len(lad)) - 1]


def week_key(day: dt.date) -> str:
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def period_key(kind: str, day: dt.date) -> str:
    """Zaderjka — har kuni noldan, kech qolish — har hafta (dushanbadan) noldan."""
    return day.isoformat() if kind == "delay" else week_key(day)


def count(db, pid: int, kind: str, day: dt.date) -> int:
    """Shu davrdagi (bugun / shu hafta) zaderjka yoki kech qolishlar soni. Ega bekor qilgan jarima sanalmaydi."""
    return db.scalar("SELECT COUNT(*) FROM strikes s LEFT JOIN adj a ON a.id=s.adj_id WHERE s.person_id=? AND s.kind=? "
                     "AND s.period=? AND (s.adj_id IS NULL OR a.cancelled=0)", (pid, kind, period_key(kind, day)))


def next_amount(db, pid: int, kind: str, day: dt.date) -> tuple[int, float]:
    """Keyingisi nechanchi va qancha bo'ladi."""
    n = count(db, pid, kind, day) + 1
    return n, amount_for(ladder(db, kind), n)


def episode_of(db, pid: int, anchor: int, episode_sec: int):
    """Shu zaderjka oldingisining davomimi (N daqiqa ichida, o'sha kuni) — o'sha zaderjka yozuvi yoki None."""
    if episode_sec <= 0:
        return None
    return db.one("SELECT * FROM strikes WHERE person_id=? AND kind='delay' AND ts BETWEEN ? AND ? ORDER BY ts LIMIT 1",
                  (pid, anchor - episode_sec, anchor + episode_sec))


def strike(db, pid: int, kind: str, day: dt.date, ts: int, folder_id: int | None = None, ref: str = "",
           note: str = "", minutes: int | None = None) -> dict | None:
    """Bitta «zaderjka» yoki «kech qolish» yoziladi. -> {"n", "usd", "adj_id"} yoki None (jarimalar o'chiq).
    Kech qolish: minutes — necha daqiqa kech (summa jadvaldan), n — haftadagi nechanchisi (faqat xabar uchun)."""
    if not on(db, kind):
        return None
    if kind == "late":
        n, usd = count(db, pid, kind, day) + 1, late_amount(late_table(db), int(minutes or 0))
    else:
        n, usd = next_amount(db, pid, kind, day)
    adj_id = None
    if usd > 0:
        from .kassa import add_adj
        adj_id = add_adj(db, pid, "fine", usd, day.isoformat(), source=SOURCE[kind], note=(note or ordinal(n, kind))[:300])
    db.run("INSERT INTO strikes(person_id, kind, period, day, ts, n, usd, folder_id, ref, adj_id) "
           "VALUES(?,?,?,?,?,?,?,?,?,?)", (pid, kind, period_key(kind, day), day.isoformat(), int(ts), n, usd, folder_id,
                                          ref, adj_id))
    return {"n": n, "usd": usd, "adj_id": adj_id}


def ordinal(n: int, kind: str) -> str:
    """Ruscha (guruh uchun): «2-я за сегодня» / «2-е опоздание за неделю»."""
    return f"{n}-я за сегодня" if kind == "delay" else f"{n}-е опоздание за неделю"


def delay_line(person, res: dict) -> str:
    """«💸 @baxa, вам штраф 10 $ за задержку (2-я за сегодня)» — «Проёб» uchun."""
    from .gtext import esc
    who = esc(P.mention(person))
    if res["usd"] > 0:
        return f"💸 {who}, вам штраф {money(res['usd'])} $ за задержку ({ordinal(res['n'], 'delay')})"
    return f"⚠️ {who} — задержка ({ordinal(res['n'], 'delay')}), в этот раз без штрафа"


def late_tail(res: dict | None) -> str:
    """Kech qolish xabarining davomi: « — вам штраф 10 $ (2-е опоздание за неделю)»."""
    if not res:
        return ""
    if res["usd"] > 0:
        return f" — вам штраф {money(res['usd'])} $ ({ordinal(res['n'], 'late')})"
    return f" ({ordinal(res['n'], 'late')}, без штрафа)"


def rows_for(db, day: dt.date) -> list[dict]:
    """📋 Bugun (zaderjka) va shu hafta (kech qolish): har xodim — nechta va jami $ (bekor qilinganlarsiz)."""
    out: dict[int, dict] = {}
    for kind in ("delay", "late"):
        for r in db.all("SELECT s.person_id, COUNT(*) n, SUM(CASE WHEN a.id IS NULL OR a.cancelled=0 THEN s.usd ELSE 0 "
                        "END) usd FROM strikes s LEFT JOIN adj a ON a.id=s.adj_id WHERE s.kind=? AND s.period=? "
                        "AND (s.adj_id IS NULL OR a.cancelled=0) GROUP BY s.person_id", (kind, period_key(kind, day))):
            d = out.setdefault(r["person_id"], {"delay": 0, "late": 0, "usd_delay": 0.0, "usd_late": 0.0})
            d[kind] = r["n"]
            d[f"usd_{kind}"] = float(r["usd"] or 0)
    rows = []
    for pid, d in out.items():
        p = P.person(db, pid)
        if p is not None:
            rows.append(dict(d, p=p))
    rows.sort(key=lambda x: (-(x["usd_delay"] + x["usd_late"]), -(x["delay"] + x["late"]), x["p"]["name"].lower()))
    return rows
