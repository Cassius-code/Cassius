"""🔒 Qattiq rejim (RD-bo'lim reglamenti asosida, egasi tanlagan hisob bilan). Yoqilsa — oddiy jarimalar
(papka jarimasi, kechikishga daqiqasiga) ishlamaydi, o'rniga:

🕘 Kechikish — o'sha kungi zp dan: 15 daqiqagacha — ogohlantirish; 15–30 — 15%; 30–60 — 30%; 60+ — 50%.
   Haftada 3-kechikishdan boshlab — yana 10% (o'sha kungi zp dan). Summa kechki hisobotdan keyin aniqlanadi.
🐢 Sekin javob (limitdan oshgan zaderjka), har hafta yangidan: 1-marta — ogohlantirish; 2-marta — $15 × xodim %;
   3-dan boshlab har biri — $25 × xodim %. Kimga: o'sha kuni o'sha papkada ishlayotganlarga.
🚪 Papkani tashlab ketish: lid kutib turibdi, xodim tanaffus demasdan yo'q — 15+ daqiqa: $15 × %; 60+: jami $40 × %.
   Shu paytdagi sekin javoblar alohida jarima bo'lmaydi («bitta voqea — bitta jarima»).

Jarima faqat xodimlarga (kassa turi — xodim). «$ × xodim foizi»: masalan $15 × 41% = $6.15."""
from __future__ import annotations

import logging
from datetime import date

from . import kassa as K
from . import people as P
from .gtext import esc, head, small
from .timeutil import day_start, is_work_time, local_date

log = logging.getLogger("strict")

LATE_WARN = 15                               # shu daqiqagacha — faqat ogohlantirish
LATE_TIERS = ((60, 50.0), (30, 30.0), (15, 15.0))   # (daqiqadan, kunlik zp %) — kattasidan tekshiriladi
LATE_WEEK_N, LATE_WEEK_EXTRA = 3, 10.0      # haftada 3-kechikishdan boshlab — yana 10%
SLOW_USD = (0.0, 15.0, 25.0)                # sekin javob: 1-marta — ogohlantirish, 2-marta — $15, 3+ — $25
AWAY_STEPS = ((15, 15.0), (60, 40.0))       # tashlab ketish: (daqiqa, jami $)


def on(db) -> bool:
    return db.flag("strict_on") and db.flag("fines_enabled")


def is_worker(p) -> bool:
    return p is not None and p["kassa_kind"] == "worker"


def share(db, pid: int, day) -> float:
    """Xodim foizi (o'sha kun uchun) — 0..1."""
    return max(0.0, K.percent_on(db, pid, day)) / 100.0


def money(v: float) -> str:
    v = K.r2(v)
    return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:.2f}"


def _week(day: date) -> str:
    return K.week_start(day).isoformat()


# ───────────────────────── 🕘 kechikish
def late_rule(db, pid: int, day: date, late_min: int) -> tuple[float, float]:
    """-> (asosiy %, qo'shimcha %). 0, 0 — ogohlantirish (15 daqiqagacha)."""
    if late_min < LATE_WARN:
        return 0.0, 0.0
    base = next(p for m, p in LATE_TIERS if late_min >= m)
    ws = K.week_start(day)
    n = db.scalar("SELECT COUNT(*) FROM attendance WHERE person_id=? AND day BETWEEN ? AND ? AND late_min>0",
                  (pid, ws.isoformat(), day.isoformat()))
    return base, (LATE_WEEK_EXTRA if n >= LATE_WEEK_N else 0.0)


def late_fine(db, person, day: date, late_min: int) -> float:
    """Kechikish jarimasi (kunlik zp ning % i). Summa (usd) — hisobotdan keyin settle() bilan. -> umumiy %."""
    if not is_worker(person):
        return 0.0
    base, extra = late_rule(db, person["id"], day, late_min)
    pct = base + extra
    if pct <= 0:
        return 0.0
    note = f"опоздание {late_min} мин — {pct:g}% дневной ЗП" + (" (3-е опоздание за неделю: +10%)" if extra else "")
    aid = K.add_adj(db, person["id"], "fine", 0.0, day.isoformat(), source="late", note=note)
    db.run("UPDATE adj SET pct=? WHERE id=?", (pct, aid))
    settle_one(db, aid)
    return pct


def late_note(db, person, day: date, late_min: int) -> str:
    """«Опоздание» xabari tagiga (qattiq rejimda): jarima foizi yoki ogohlantirish."""
    if not is_worker(person):
        return ""
    if late_min < LATE_WARN:
        return small("⚠️ предупреждение — до 15 мин без штрафа")
    a = db.one("SELECT pct, note FROM adj WHERE person_id=? AND day=? AND source='late' AND pct IS NOT NULL "
               "AND cancelled=0 ORDER BY id DESC LIMIT 1", (person["id"], day.isoformat()))
    if a is None:
        return ""
    extra = " (3-е опоздание за неделю: +10%)" if "+10%" in (a["note"] or "") else ""
    return small(f"💸 штраф {a['pct']:g}% дневной ЗП{extra}")


def settle_one(db, aid: int, cache: dict | None = None) -> None:
    a = db.one("SELECT id, person_id, day, pct, usd FROM adj WHERE id=?", (aid,))
    if a is None or a["pct"] is None:
        return
    key = (a["person_id"], a["day"])
    if cache is not None and key in cache:
        zp = cache[key]
    else:
        zp = K.day_zp(db, a["person_id"], a["day"])
        if cache is not None:
            cache[key] = zp
    usd = K.r2(float(a["pct"]) / 100.0 * zp)
    if abs(usd - float(a["usd"] or 0)) > 0.004:
        db.run("UPDATE adj SET usd=? WHERE id=?", (usd, aid))


def settle(db, today: date, days: int = 8) -> None:
    """Foizli jarimalar summasini kunlik zp bo'yicha yangilash (hisobot keldi / chek tuzatildi)."""
    since = date.fromordinal(today.toordinal() - days).isoformat()
    cache: dict = {}
    for a in db.all("SELECT id FROM adj WHERE pct IS NOT NULL AND cancelled=0 AND day>=?", (since,)):
        settle_one(db, a["id"], cache)


# ───────────────────────── 🐢 sekin javob
def away_overlaps(db, pid: int, since: int, now: int) -> bool:
    """Shu davrda xodim «joyida yo'q» deb jarimalanganmi (bitta voqea — bitta jarima)."""
    return db.one("SELECT 1 FROM strict_events WHERE person_id=? AND kind='away' AND ts<=? AND "
                  "(ended_ts IS NULL OR ended_ts>=?)", (pid, now, since)) is not None


async def slow(tracker, f, rows, now: int) -> None:
    """Papkada zaderjka bo'ldi (lid limitdan ortiq kutdi): papkada ishlayotgan har xodimga — haftalik hisob."""
    db = tracker.db
    if not on(db) or not rows:
        return
    day = local_date(now, tracker.tz)
    week = _week(day)
    since = min(r["wait_since"] for r in rows)
    lines, fined = [], False
    for p in tracker.fine_people(f["id"], day):
        if not is_worker(p) or away_overlaps(db, p["id"], since, now):
            continue
        n = db.scalar("SELECT COUNT(*) FROM strict_events WHERE person_id=? AND kind='slow' AND week=?",
                      (p["id"], week)) + 1
        base = SLOW_USD[min(n, len(SLOW_USD)) - 1]
        amount = K.r2(base * share(db, p["id"], day)) if base else 0.0
        aid = None
        if amount > 0:
            aid = K.add_adj(db, p["id"], "fine", amount, day.isoformat(), source="strict_slow",
                            note=f"долгий ответ — {n}-й раз за неделю")
            fined = True
        db.run("INSERT INTO strict_events(person_id, kind, week, day, ts, level, adj_id, folder_id) "
               "VALUES(?,?,?,?,?,?,?,?)", (p["id"], "slow", week, day.isoformat(), now, n, aid, f["id"]))
        who = esc(P.mention(p))
        if amount > 0:
            lines.append(f"💸 {who} — {n}-й раз за неделю: штраф <b>{money(amount)} $</b>")
        elif base:
            lines.append(f"⚠️ {who} — {n}-й раз за неделю: штраф не начислен (не задан % сотрудника)")
        else:
            lines.append(f"⚠️ {who} — 1-й раз за неделю: предупреждение")
    if not lines:
        return
    limit = db.get_int("limit_minutes", 20)
    text = "\n".join([head(f["name"], f"долгий ответ ({limit}+ мин)")] + lines)
    try:
        await tracker.notifier.send_group(text, trash=None if fined else "info")   # jarima bo'lsa — qoladi
    except Exception as exc:
        log.warning("Qattiq rejim (sekin javob) xabari yuborilmadi: %s", exc)


# ───────────────────────── 🚪 papkani tashlab ketish
def _last_act(db, p, day: date, arrived: int, act: int | None) -> int:
    br = db.scalar("SELECT MAX(end_ts) FROM breaks WHERE person_id=? AND end_ts IS NOT NULL AND start_ts>=?",
                   (p["id"], arrived - 6 * 3600)) or 0
    return max(arrived or 0, act or 0, br)


def _waiting(tracker, folders: list[int], now: int) -> int:
    """Xodim papkalarida eng uzoq kutayotgan lid — necha soniya (ish vaqtida; stavka va ⚡/💊 hisobga kirmaydi)."""
    from .rules import label_excluded, skip_list
    if not folders:
        return 0
    skip = skip_list(tracker.db)
    best = 0
    for th in tracker.db.all("SELECT chat_id, topic_id, wait_since FROM threads WHERE wait_since IS NOT NULL "
                             "AND stavka<>'on'"):
        fid = tracker.chat_folder.get(th["chat_id"])
        if fid not in folders or label_excluded(tracker.label(th["chat_id"], th["topic_id"]), skip):
            continue
        best = max(best, tracker.elapsed(fid, th["wait_since"], now))
    return best


def _away_text(p, f_names: str, minutes: int, amount: float, note: str = "") -> str:
    return "\n".join(x for x in [
        f"<b>🚪 Нет на месте — {minutes}+ мин</b>",
        f"{esc(P.mention(p))} · {esc(f_names)} — лиды ждут, перерыв не объявлен",
        small(f"💸 штраф {money(amount)} $" + (f" {note}" if note else "")) if amount > 0 else
        small("⚠️ штраф не начислен (не задан % сотрудника)")] if x)


async def away_tick(ctx, now: int) -> None:
    """Har tickda: ishga kelgan, tanaffusda emas xodim — lid kutib turibdi, lekin u 15+ daqiqa hech narsa yozmagan."""
    db, tr = ctx.db, ctx.tracker
    if not on(db) or not db.flag("bot_enabled") or not db.flag("delay_enabled"):
        return
    ws, we = tr.work_window()
    work = is_work_time(now, tr.tz, ws, we)
    day = local_date(now, tr.tz)
    active = {r["person_id"]: r for r in db.all("SELECT * FROM strict_events WHERE kind='away' AND ended_ts IS NULL")}
    if not work:
        for ev in active.values():
            db.run("UPDATE strict_events SET ended_ts=? WHERE id=?", (now, ev["id"]))
        return
    for row in db.all("SELECT * FROM attendance WHERE day=? AND arrived_ts IS NOT NULL", (day.isoformat(),)):
        p = P.person(db, row["person_id"])
        if not is_worker(p) or not p["active"]:
            continue
        ev = active.get(p["id"])
        last = _last_act(db, p, day, row["arrived_ts"], row["last_act_ts"])
        on_break = db.one("SELECT 1 FROM breaks WHERE person_id=? AND end_ts IS NULL AND start_ts>=?",
                          (p["id"], day_start(now, tr.tz))) is not None
        if ev is not None and (on_break or last > (ev["act_ts"] or 0)):
            db.run("UPDATE strict_events SET ended_ts=? WHERE id=?", (now if on_break else last, ev["id"]))
            continue                                        # qaytdi (yoki tanaffus aytdi)
        if on_break:
            continue
        folders = [f["id"] for f in P.folders(db) if f["delay_on"] and p["id"] in
                   {x["id"] for x in P.folder_people(db, f["id"])}]
        absence = min(now - last, _waiting(tr, folders, now))
        names = ", ".join(f["name"] for f in P.folders(db) if f["id"] in folders)
        pct = share(db, p["id"], day)
        if ev is None:
            mins, usd = AWAY_STEPS[0]
            if absence < mins * 60:
                continue
            amount = K.r2(usd * pct)
            aid = K.add_adj(db, p["id"], "fine", amount, day.isoformat(), source="strict_away",
                            note=f"нет на месте {mins}+ мин") if amount > 0 else None
            gid = mid = None
            try:
                gid, mid = await ctx.notifier.send_group(_away_text(p, names, mins, amount),
                                                         trash=None if amount > 0 else "info")
            except Exception as exc:
                log.warning("Qattiq rejim (joyida yo'q) xabari yuborilmadi: %s", exc)
            db.run("INSERT INTO strict_events(person_id, kind, week, day, ts, level, adj_id, folder_id, act_ts, gid, "
                   "mid) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (p["id"], "away", _week(day), day.isoformat(), now, 1, aid,
                                                         folders[0] if folders else None, last, gid, mid))
            continue
        mins, usd = AWAY_STEPS[1]
        if ev["level"] >= 2 or absence < mins * 60:
            continue
        add = K.r2((usd - AWAY_STEPS[0][1]) * pct)          # 15 → jami 40: yana 25 × %
        total = K.r2(usd * pct)
        if add > 0:
            K.add_adj(db, p["id"], "fine", add, day.isoformat(), source="strict_away", note=f"нет на месте {mins}+ мин")
        db.run("UPDATE strict_events SET level=2 WHERE id=?", (ev["id"],))
        if ev["mid"]:
            try:
                await ctx.notifier.edit_group(ev["gid"], ev["mid"], _away_text(p, names, mins, total, "(всего)"))
            except Exception as exc:
                log.info("Qattiq rejim xabari tahrirlanmadi: %s", exc)
