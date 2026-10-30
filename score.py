"""🏆 Haftalik ball (0–100) — har xodimga, faqat raqamlardan (xabar matni o'qilmaydi). 4 qism, har biri 25 ball:

⚡ Tezlik    — javoblarining o'rtacha (mediana) vaqti, ish vaqtida: 3 daqiqagacha — 25, limitda (20 daq) va undan
               ko'p — 0, oralig'i — teng bo'lib.
🚨 Zaderjka  — har 100 javobga nechta «задержка» (o'sha kuni o'sha papkada ishlagan bo'lsa): 0 — 25, 10 va ko'p — 0.
💳 Karta     — javob bergan lidlaridan nechtasiga karta ketdi, jamoa o'rtachasiga nisbatan: 1.5 barobar va ko'p — 25,
               o'rtacha — ~17, karta yo'q — 0. Jamoada hali karta yo'q bo'lsa — bu qism hisobga olinmaydi.
🕘 Intizom   — 25 dan: har 5 daqiqa kechikish — 1 ball, eslatmadan keyin ham javob bermaslik (jarima) — 5 ball.

Haftada 20 tadan kam javob bergan xodimga ball qo'yilmaydi («ma'lumot kam»). Pulga bog'lanmagan — faqat ko'rsatadi.
🔥 Seriya — ketma-ket necha ish kuni zaderjkasiz (ishga kelgan kunlar)."""
from __future__ import annotations

import datetime as dt
import statistics

from . import people as P
from .timeutil import at

PART = 25
MIN_REPLIES = 20
FAST = 3 * 60                 # shu vaqtgacha javob — tezlik to'liq ball
DELAY_ZERO = 10.0             # har 100 javobga shuncha zaderjka — 0 ball
CARD_TOP = 1.5                # jamoa o'rtachasidan shuncha barobar — to'liq ball
LATE_STEP = 5                 # har shuncha daqiqa kechikish — 1 ball
REMIND_COST = 5               # eslatmadan keyin javob yo'q (jarima) — shuncha ball


def week_bounds(day: dt.date, tz) -> tuple[dt.date, dt.date, int, int]:
    s = day - dt.timedelta(days=day.weekday())
    e = s + dt.timedelta(days=6)
    return s, e, at(s, dt.time(0, 0), tz), at(e + dt.timedelta(days=1), dt.time(0, 0), tz)


def _on_duty(tracker, folder_id: int, day: dt.date) -> list[int]:
    """O'sha kuni o'sha RD da ishlagan xodim(lar) — 📅 Bugun kim qayerda bo'yicha."""
    return [p["id"] for p in tracker.fine_people(folder_id, day)]


def delays_by_person(db, tracker, s_ts: int, e_ts: int) -> dict[int, list[str]]:
    """Har xodim: qaysi kunlari zaderjka bo'lgan (o'sha kuni o'sha papkada ishlagan bo'lsa). -> {pid: [kun, ...]}."""
    out: dict[int, list[str]] = {}
    for a in db.all("SELECT folder_id, created_ts FROM alerts WHERE created_ts>=? AND created_ts<? AND status<>'void'",
                    (s_ts, e_ts)):
        day = dt.datetime.fromtimestamp(a["created_ts"], tracker.tz).date()
        for pid in _on_duty(tracker, a["folder_id"], day):
            out.setdefault(pid, []).append(day.isoformat())
    return out


def compute(ctx, s: dt.date, e: dt.date) -> list[dict]:
    """Davr uchun har xodimning bali va qismlari. Ball kamayib borish tartibida (ma'lumoti kamlar — oxirida)."""
    db, tr, tz = ctx.db, ctx.tracker, ctx.tz
    s_ts, e_ts = at(s, dt.time(0, 0), tz), at(e + dt.timedelta(days=1), dt.time(0, 0), tz)
    s_day, e_day = s.isoformat(), e.isoformat()
    limit = max(FAST + 60, db.get_int("limit_minutes", 20) * 60)
    reply: dict[int, list] = {}
    answered: dict[int, set] = {}
    for r in db.all("SELECT person_id, chat_id, topic_id, work_seconds FROM replies WHERE reply_ts>=? AND reply_ts<? "
                    "AND person_id IS NOT NULL", (s_ts, e_ts)):
        reply.setdefault(r["person_id"], []).append(r["work_seconds"])
        answered.setdefault(r["person_id"], set()).add((r["chat_id"], r["topic_id"]))
    carded: dict[int, set] = {}
    for r in db.all("SELECT person_id, chat_id, topic_id FROM cards WHERE ts>=? AND ts<? AND person_id IS NOT NULL",
                    (s_ts, e_ts)):
        carded.setdefault(r["person_id"], set()).add((r["chat_id"], r["topic_id"]))
    delays = delays_by_person(db, tr, s_ts, e_ts)
    late = {r["person_id"]: int(r["m"] or 0) for r in db.all(
        "SELECT person_id, SUM(late_min) m FROM attendance WHERE day BETWEEN ? AND ? GROUP BY person_id", (s_day, e_day))}
    reminds = {r["person_id"]: r["n"] for r in db.all(       # eslatmadan keyin ham javobsiz — 1 ta zaderjka (💸)
        "SELECT s.person_id, COUNT(*) n FROM strikes s LEFT JOIN adj a ON a.id=s.adj_id WHERE s.kind='delay' "
        "AND (s.adj_id IS NULL OR a.cancelled=0) AND s.day BETWEEN ? AND ? GROUP BY s.person_id", (s_day, e_day))}
    staff = {p["id"]: p for p in db.all("SELECT DISTINCT p.* FROM people p JOIN folder_people fp ON fp.person_id=p.id "
                                         "WHERE p.active=1")}
    for pid in set(reply) | set(carded):
        if pid not in staff:
            p = P.person(db, pid)
            if p is not None and p["active"]:
                staff[pid] = p
    enough = [pid for pid in staff if len(reply.get(pid, [])) >= MIN_REPLIES]
    team_ans = sum(len(answered.get(pid, ())) for pid in enough)
    team_card = sum(len(carded.get(pid, ())) for pid in enough)
    team_conv = team_card / team_ans if team_ans else 0.0
    streaks = streaks_for(ctx, list(staff), e)
    rows = []
    for pid, p in staff.items():
        n = len(reply.get(pid, []))
        med = statistics.median(reply[pid]) if n else None
        d = len(delays.get(pid, []))
        row = {"p": p, "n": n, "median": med, "delays": d, "late_min": late.get(pid, 0), "reminds": reminds.get(pid, 0),
               "cards": len(carded.get(pid, ())), "leads": len(answered.get(pid, ())), "score": None, "parts": {},
               "streak": streaks.get(pid, 0)}
        if n >= MIN_REPLIES:
            parts = {}
            parts["speed"] = PART * max(0.0, min(1.0, (limit - med) / (limit - FAST))) if med is not None else 0.0
            parts["delay"] = PART * max(0.0, 1.0 - (100.0 * d / n) / DELAY_ZERO)
            if team_conv > 0:
                conv = len(carded.get(pid, ())) / max(1, row["leads"])
                parts["card"] = PART * min(1.0, conv / team_conv / CARD_TOP)
            parts["disc"] = max(0.0, PART - row["late_min"] / LATE_STEP - REMIND_COST * row["reminds"])
            row["parts"] = {k: round(v) for k, v in parts.items()}
            row["score"] = round(100.0 * sum(parts.values()) / (PART * len(parts)))
        rows.append(row)
    rows.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0), -x["n"], x["p"]["name"].lower()))
    return rows


def streaks_for(ctx, pids: list[int], upto: dt.date, back: int = 30) -> dict[int, int]:
    """🔥 Ketma-ket necha ish kuni zaderjkasiz (ishga kelgan kunlar; bugun hali tugamagan — kechadan boshlab)."""
    db, tr, tz = ctx.db, ctx.tracker, ctx.tz
    today = dt.datetime.fromtimestamp(ctx.clock(), tz).date()
    last = min(upto, today - dt.timedelta(days=1))
    start = last - dt.timedelta(days=back)
    worked: dict[int, set] = {}
    for r in db.all("SELECT person_id, day FROM attendance WHERE arrived_ts IS NOT NULL AND day BETWEEN ? AND ?",
                    (start.isoformat(), last.isoformat())):
        worked.setdefault(r["person_id"], set()).add(r["day"])
    bad = {pid: set(days) for pid, days in delays_by_person(
        db, tr, at(start, dt.time(0, 0), tz), at(last + dt.timedelta(days=1), dt.time(0, 0), tz)).items()}
    out = {}
    for pid in pids:
        n, day = 0, last
        while day >= start:
            iso = day.isoformat()
            if iso in worked.get(pid, ()):
                if iso in bad.get(pid, ()):
                    break
                n += 1
            day -= dt.timedelta(days=1)
        out[pid] = n
    return out


def advice(row: dict, lang: str = "uz") -> str:
    """Bitta qator maslahat — eng past qismga qarab (faqat raqamlardan)."""
    ru = lang == "ru"
    parts = row["parts"]
    if not parts:
        return "мало данных" if ru else "ma'lumot kam"
    weakest = min(parts, key=lambda k: parts[k])
    if parts[weakest] >= 20:
        return "отличная неделя 👏" if ru else "zo'r hafta 👏"
    mins = round((row["median"] or 0) / 60)
    tips = {"speed": (f"o'rtacha {mins} daqiqada javob beradi — tezroq javob kerak",
                      f"отвечает в среднем за {mins} мин — нужно быстрее"),
            "delay": (f"zaderjka ko'p ({row['delays']}) — lidlarni kuzatib borish kerak",
                      f"много задержек ({row['delays']}) — следить за лидами"),
            "card": ("tez javob beradi, lekin karta kam — sotishni kuchaytirish kerak" if parts.get("speed", 0) >= 18
                     else "karta kam — sotishni kuchaytirish kerak",
                     "отвечает быстро, но карт мало — усилить продажи" if parts.get("speed", 0) >= 18
                     else "мало карт — усилить продажи"),
            "disc": ("kechikish va eslatmalar — intizom kerak", "опоздания и напоминания — нужна дисциплина")}
    uz, rus = tips[weakest]
    return rus if ru else uz


def parts_line(row: dict) -> str:
    icons = (("speed", "⚡"), ("delay", "🚨"), ("card", "💳"), ("disc", "🕘"))
    return " ".join(f"{icon}{row['parts'][k]}" for k, icon in icons if k in row["parts"])


def person_line(ctx, pid: int, s: dt.date, e: dt.date) -> str:
    """Xodimning zp xabariga (ruscha, oddiy matn): «🏆 Балл недели: 86 из 100 · 🔥 5 дней без задержек»."""
    try:
        row = next((x for x in compute(ctx, s, e) if x["p"]["id"] == pid), None)
    except Exception:
        return ""
    if row is None or row["score"] is None:
        return ""
    line = f"🏆 Балл недели: {row['score']} из 100"
    if row["streak"] >= 3:
        line += f" · 🔥 {row['streak']} дн. без задержек"
    return line + f"\n{advice(row, 'ru')}"
