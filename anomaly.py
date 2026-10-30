"""📈 G'ayrioddiy o'zgarish (egasiga, haftada bir — dushanba ertalab): o'tgan hafta oldingi 3 haftaning o'rtachasidan
keskin farq qilgan narsalar. Faqat raqamlar (xabar matni o'qilmaydi):
* xodim: javob tezligi (mediana), zaderjkalar, kech qolishlar, kartalar, kassa;
* RD: yangi lidlar, kartalar, zaderjkalar.
Kichik raqamlar (tasodif) chiqmaydi: kamida N ta bo'lsa va farq ±35% dan katta bo'lsa."""
from __future__ import annotations

import datetime as dt
import statistics

from . import people as P
from .timeutil import at

CHANGE = 0.35                 # shuncha va ko'p farq — g'ayrioddiy
WEEKS_BACK = 3                # solishtirish: oldingi shuncha haftaning o'rtachasi


def _bounds(mon: dt.date, tz) -> tuple[int, int, str, str]:
    s, e = mon, mon + dt.timedelta(days=6)
    return at(s, dt.time(0, 0), tz), at(e + dt.timedelta(days=1), dt.time(0, 0), tz), s.isoformat(), e.isoformat()


def week_metrics(db, mon: dt.date, tz) -> dict:
    """Bitta hafta: {"p": {pid: {...}}, "f": {fid: {...}}}."""
    s_ts, e_ts, s_d, e_d = _bounds(mon, tz)
    p: dict[int, dict] = {}
    f: dict[int, dict] = {}

    def P_(pid):
        return p.setdefault(pid, {"reply": [], "delays": 0, "late": 0, "cards": 0, "kassa": 0})

    def F_(fid):
        return f.setdefault(fid, {"leads": 0, "cards": 0, "delays": 0})
    for r in db.all("SELECT person_id, work_seconds FROM replies WHERE reply_ts>=? AND reply_ts<? AND person_id IS NOT "
                    "NULL", (s_ts, e_ts)):
        P_(r["person_id"])["reply"].append(r["work_seconds"])
    for r in db.all("SELECT person_id, COUNT(*) n FROM strikes WHERE kind='delay' AND day BETWEEN ? AND ? "
                    "GROUP BY person_id", (s_d, e_d)):
        P_(r["person_id"])["delays"] = r["n"]
    for r in db.all("SELECT person_id, COUNT(*) n FROM attendance WHERE late_min>0 AND day BETWEEN ? AND ? "
                    "GROUP BY person_id", (s_d, e_d)):
        P_(r["person_id"])["late"] = r["n"]
    for r in db.all("SELECT person_id, folder_id, COUNT(*) n FROM cards WHERE ts>=? AND ts<? GROUP BY person_id, "
                    "folder_id", (s_ts, e_ts)):
        if r["person_id"]:
            P_(r["person_id"])["cards"] += r["n"]
        if r["folder_id"]:
            F_(r["folder_id"])["cards"] += r["n"]
    for r in db.all("SELECT r.person_id, SUM(ch.amount) raw FROM checks ch JOIN reports r ON r.id=ch.report_id "
                    "WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? GROUP BY r.person_id", (s_d, e_d)):
        if r["person_id"]:
            P_(r["person_id"])["kassa"] = int(r["raw"] or 0)
    for r in db.all("SELECT folder_id, COUNT(*) n FROM alerts WHERE created_ts>=? AND created_ts<? AND status<>'void' "
                    "GROUP BY folder_id", (s_ts, e_ts)):
        F_(r["folder_id"])["delays"] = r["n"]
    for r in db.all("SELECT c.folder_id, COUNT(*) n FROM topics t JOIN chats c ON c.chat_id=t.chat_id WHERE "
                    "t.created_ts>=? AND t.created_ts<? AND t.topic_id>1 GROUP BY c.folder_id", (s_ts, e_ts)):
        F_(r["folder_id"])["leads"] = r["n"]
    return {"p": p, "f": f}


def _med(xs: list) -> float | None:
    return statistics.median(xs) if xs else None


def _ratio_text(cur: float, base: float, lang: str) -> str:
    if base <= 0:
        return ""
    k = cur / base
    if k >= 1.9:
        return f"{k:.1f} barobar ko'paydi".replace(".0 ", " ") if lang != "ru" else f"выросли в {k:.1f} раза"
    if k <= 0.53:
        return (f"{1 / k:.1f} barobar kamaydi" if lang != "ru" else f"упали в {1 / k:.1f} раза").replace(".0 ", " ")
    d = round((k - 1) * 100)
    return (f"{abs(d)}% {'ko‘paydi' if d > 0 else 'kamaydi'}" if lang != "ru" else
            f"{'выросли' if d > 0 else 'упали'} на {abs(d)}%")


def changes(db, mon: dt.date, tz, lang: str = "uz") -> list[str]:
    """O'tgan hafta (dushanbasi — mon) va oldingi 3 hafta o'rtachasi. -> qatorlar (eng kattasi oldin)."""
    cur = week_metrics(db, mon, tz)
    prev = [week_metrics(db, mon - dt.timedelta(days=7 * i), tz) for i in range(1, WEEKS_BACK + 1)]
    ru = lang == "ru"
    out: list[tuple[float, str]] = []

    def avg(kind: str, key: str, field: str) -> float | None:
        vals = [w[kind].get(key, {}).get(field) for w in prev]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None
    names = {r["id"]: r["name"] for r in db.all("SELECT id, name FROM people")}
    for pid, m in cur["p"].items():
        name = names.get(pid)
        if not name:
            continue
        med = _med(m["reply"])
        prev_meds = [_med(w["p"].get(pid, {}).get("reply") or []) for w in prev]
        prev_meds = [x for x in prev_meds if x is not None]
        if med is not None and prev_meds and len(m["reply"]) >= 20 and statistics.mean(prev_meds) >= 30:
            base = statistics.mean(prev_meds)
            k = med / base
            if abs(k - 1) >= CHANGE:
                d = round(abs(k - 1) * 100)
                mm = (f"{base / 60:.1f} → {med / 60:.1f} daq" if not ru else f"{base / 60:.1f} → {med / 60:.1f} мин")
                txt = (f"🐢 {name} bu hafta {d}% sekinroq javob berdi ({mm})" if k > 1 else
                       f"⚡ {name} bu hafta {d}% tezroq javob berdi ({mm})") if not ru else (
                    f"🐢 {name} на этой неделе отвечал на {d}% медленнее ({mm})" if k > 1 else
                    f"⚡ {name} на этой неделе отвечал на {d}% быстрее ({mm})")
                out.append((abs(k - 1), txt))
        for field, icon, uz, rus, minimum in (("delays", "🚨", "zaderjkalari", "задержки", 3),
                                              ("late", "🕘", "kech qolishlari", "опоздания", 2),
                                              ("cards", "💳", "kartalari", "карты", 8),
                                              ("kassa", "💵", "kassasi", "касса", 3000)):
            base = avg("p", pid, field)
            v = m[field]
            if base is None or max(v, base) < minimum:
                continue
            if base == 0 and v >= minimum:
                txt = (f"{icon} {name}: {uz} paydo bo'ldi ({v})" if not ru else f"{icon} {name}: появились {rus} ({v})")
                out.append((1.0, txt))
                continue
            if base and abs(v / base - 1) >= CHANGE:
                shown = (f"{int(base)} → {v}" if field != "kassa" else f"{int(base):,} → {v:,}".replace(",", " "))
                out.append((abs(v / base - 1), f"{icon} {name}: {rus if ru else uz} {_ratio_text(v, base, lang)} "
                                                f"({shown})"))
    fnames = {f["id"]: f["name"] for f in P.folders(db)}
    for fid, m in cur["f"].items():
        name = fnames.get(fid)
        if not name:
            continue
        for field, icon, uz, rus, minimum in (("leads", "🆕", "yangi lidlar", "новые лиды", 10),
                                              ("cards", "💳", "kartalar", "карты", 10),
                                              ("delays", "🚨", "zaderjkalar", "задержки", 5)):
            base = avg("f", fid, field)
            v = m[field]
            if base is None or max(v, base) < minimum or not base:
                continue
            if abs(v / base - 1) >= CHANGE:
                where = f"{name}:" if ru else f"{name} da"
                out.append((abs(v / base - 1), f"{icon} {where} {rus if ru else uz} {_ratio_text(v, base, lang)} "
                                                f"({int(base)} → {v})"))
    out.sort(key=lambda x: -x[0])
    return [t for _k, t in out[:12]]


async def weekly(ctx, now: int) -> bool:
    """Dushanba 09:00 dan keyin bir marta: o'tgan hafta bo'yicha egaga (o'zgarish bo'lsa)."""
    db = ctx.db
    if not db.flag("an_anomaly") or not db.flag("bot_enabled"):
        return False
    t = dt.datetime.fromtimestamp(now, ctx.tz)
    if t.weekday() != 0 or t.hour < 9:
        return False
    mon = t.date() - dt.timedelta(days=7)
    if db.get("anomaly_last") >= mon.isoformat():
        return False
    db.set("anomaly_last", mon.isoformat())
    from .context import tr
    from .kassa_view import label
    from .ui import h, kb

    def build():
        from .context import LANG
        lines = changes(db, mon, ctx.tz, LANG.get() or "uz")
        head = tr(f"📈 <b>G'ayrioddiy o'zgarishlar</b> · {label(mon, mon + dt.timedelta(days=6))}",
                  f"📈 <b>Необычные изменения</b> · {label(mon, mon + dt.timedelta(days=6))}")
        sub = tr("<i>o'tgan hafta — oldingi 3 haftaning o'rtachasiga nisbatan</i>",
                 "<i>прошлая неделя — к среднему за 3 недели до неё</i>")
        return "\n".join([head, sub, "", "<blockquote>" + "\n".join(h(x) for x in lines) + "</blockquote>"]), \
            kb([(tr("📈 Batafsil", "📈 Подробнее"), "ana:lw")])
    if not changes(db, mon, ctx.tz):
        return False                                       # hammasi odatdagidek — xabar shart emas
    await ctx.notifier.send_keyed(ctx.notifier.owner_ids(), build, key=f"anomaly:{mon.isoformat()}")
    return True
