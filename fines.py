"""💸 Jarima zinapoyasi (egasi bilan kelishilgan, 2026-10-30).

* ⏰ zaderjka — «задержка» → eslatma → muhlat, shunda ham javob bo'lmasa — 1 ta. Bir vaqtda kechikkan lidlar va
  undan keyingi N daqiqa (fine_episode, 30) ichidagilari — o'sha 1 ta. Har KUNI noldan.
* 🕘 kech qolish — ish boshlanishidan N daqiqa (late_after_min, 15) va undan ko'p kech kelsa — 1 ta. Har HAFTA
  (dushanbadan) noldan.
1-si, 2-si, 3-si … — egasi yozgan summalar bo'yicha («0 5 10 20»: oxirgisi keyingilarga ham). 0 — sanaladi, lekin
pulsiz. Jarimalar o'chiq (yoki summalar yozilmagan) bo'lsa — hech narsa sanalmaydi va «штраф» so'zi chiqmaydi.
Jarima o'sha RD da shu kuni ishlayotgan xodimga (bitta RD — bitta xodim); tanaffusdagisiga — yo'q."""
from __future__ import annotations

import datetime as dt
import re

from . import people as P

KEYS = {"delay": "fine_ladder_delay", "late": "fine_ladder_late"}
SOURCE = {"delay": "remind", "late": "late"}
MAX_STEPS = 10


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
    try:
        return parse_ladder(db.get(KEYS[kind]))
    except ValueError:
        return []


def on(db, kind: str) -> bool:
    return db.flag("fines_enabled") and bool(ladder(db, kind))


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
           note: str = "") -> dict | None:
    """Bitta «zaderjka» yoki «kech qolish» yoziladi. -> {"n", "usd", "adj_id"} yoki None (jarimalar o'chiq)."""
    if not on(db, kind):
        return None
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
