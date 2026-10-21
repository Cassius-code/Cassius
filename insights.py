"""📈 Tahlil: soatlar, qotib qolgan va soviyotgan lidlar, javob tezligi → karta, g'oliblar, Push natijasi, kartalar.

Hammasi faqat VAQT va KIM YOZGANI bo'yicha hisoblanadi — xabar matni o'qilmaydi. Lid = topik (yoki oddiy chat).
Har bir son aniq qoidadan chiqadi (pastdagi izohlar); taxmin qilinmaydi — aniqlab bo'lmasa, alohida ko'rsatiladi.
"""
from __future__ import annotations

import statistics
from datetime import datetime

from . import people as P
from .gtext import esc, small, tag
from .links import message_link
from .rules import CARD_WINDOW, label_excluded, skip_list
from .timeutil import day_start, work_seconds

DAY = 86400
STALE_FLOOR_DAYS = 30          # bundan uzoq jim lid — «o'lik», ro'yxatga kirmaydi
COOL_FACTOR = 3                # odatdagidan shuncha barobar uzoq jim — soviyapti
COOL_MIN = 3600                # va kamida 1 soat (ish vaqtida)
SPEED_WINDOW = 3 * DAY         # lid birinchi yozgandan 3 kun ichida karta olsa — «kartagacha yetdi»
SPEED_BUCKETS = ((300, "≤ 5"), (600, "5–10"), (1200, "10–20"), (None, "20+"))
WIN_DAYS = 30                  # g'oliblar va tezlik — oxirgi 30 kun
MIN_LEADS = 10                 # g'oliblar formulasi: xodimda kamida shuncha lid bo'lsa
GROUP_LIMIT = 30               # «Проёб»dagi ro'yxatda bitta RD uchun eng ko'pi bilan havola
# mijozning haqiqiy xabarlari (jurnal): bot stavkasi, uning matni va «aks-sado» kirmaydi
CLIENT_DECISIONS = ("wait", "wait_more", "night", "excluded", "before", "stavka_skip")

FEATURES = ("an_heatmap", "an_stale", "an_cooling", "an_speed", "an_push", "an_cards")


def since_ts(db) -> int:
    """Karta va Push natijasi yig'ila boshlagan payt (yangi versiya ishga tushgan)."""
    return db.get_int("cards_since")


def dur(sec: float | None, lang: str) -> str:
    """Odam o'qiydigan vaqt: «45 daq», «2.5 soat», «3 kun»."""
    if sec is None:
        return "—"
    sec = max(0, float(sec))
    ru = lang == "ru"
    if sec < 3600:
        m = max(1, int(round(sec / 60)))
        return f"{m} мин" if ru else f"{m} daq"
    if sec < DAY:
        hrs = sec / 3600
        v = f"{hrs:.1f}".rstrip("0").rstrip(".") if hrs < 10 else str(int(round(hrs)))
        return f"{v} ч" if ru else f"{v} soat"
    d = int(sec // DAY)
    return f"{d} дн." if ru else f"{d} kun"


def pct(a: int, b: int) -> str:
    if not b:
        return "—"
    v = 100.0 * a / b
    return f"{v:.0f}%" if v >= 10 or v == 0 else f"{v:.1f}%"


def _excluded(tr, chat_id: int, topic_id: int, skip) -> bool:
    return label_excluded(tr.label(chat_id, topic_id), skip)


def lead_link(chat_id: int, topic_id: int, msg_id: int | None = None) -> str:
    return message_link(chat_id, msg_id or topic_id or 1, topic_id)


def _cards_by_thread(db, s_ts: int = 0, e_ts: int | None = None) -> dict:
    q = "SELECT chat_id, topic_id, COUNT(*) n, MIN(ts) first, MAX(ts) last FROM cards WHERE ts>=?"
    args = [s_ts]
    if e_ts is not None:
        q += " AND ts<?"
        args.append(e_ts)
    return {(r["chat_id"], r["topic_id"]): r for r in db.all(q + " GROUP BY chat_id, topic_id", args)}


# ═════════════════════════ 🕐 soatlar
def heatmap(db, tr, s_ts: int, e_ts: int, fid: int | None = None) -> dict:
    """Har soat (0–23): nechta lid yozdi (bir kunda bir lid bir soatda — 1 marta) va ulardan nechtasi zaderjka bo'ldi
    (javobsiz kutish shu soatda boshlangan, «задержка» ketgan). -> {hour: (leads, delays)}."""
    tz = tr.tz
    leads: dict[int, set] = {}
    q = ",".join("?" * len(CLIENT_DECISIONS))
    for r in db.all(f"SELECT ts, chat_id, topic_id FROM journal WHERE who='client' AND decision IN ({q}) "
                    "AND ts>=? AND ts<?", (*CLIENT_DECISIONS, s_ts, e_ts)):
        f = tr.chat_folder.get(r["chat_id"])
        if f is None or (fid is not None and f != fid):
            continue
        t = datetime.fromtimestamp(r["ts"], tz)
        leads.setdefault(t.hour, set()).add((t.date(), r["chat_id"], r["topic_id"]))
    delays: dict[int, int] = {}
    for r in db.all("SELECT wait_since, folder_id FROM alerts WHERE status<>'void' AND wait_since>=? AND wait_since<?",
                    (s_ts, e_ts)):
        if fid is not None and r["folder_id"] != fid:
            continue
        hr = datetime.fromtimestamp(r["wait_since"], tz).hour
        delays[hr] = delays.get(hr, 0) + 1
    hours = sorted(set(leads) | set(delays))
    return {hr: (len(leads.get(hr, ())), delays.get(hr, 0)) for hr in hours}


def heatmap_text(data: dict, lang: str) -> list[str]:
    ru = lang == "ru"
    if not data:
        return ["<i>" + ("Данных пока нет." if ru else "Hozircha ma'lumot yo'q.") + "</i>"]
    top = max(n for n, _d in data.values()) or 1
    rows = []
    for hr, (n, d) in data.items():
        bar = "█" * max(1 if n else 0, round(10 * n / top))
        rows.append(f"{hr:02d}:00 {bar:<10} {n:>3}" + (f"  🚨{d} ({pct(d, n)})" if d else ""))
    out = ["<pre>" + "\n".join(rows) + "</pre>"]
    busy = max(data.items(), key=lambda kv: kv[1][0])
    worst = max(data.items(), key=lambda kv: kv[1][1])
    from .rules import plural_leads
    out.append(("Больше всего пишут: " if ru else "Eng ko'p yozadi: ") + f"<b>{busy[0]:02d}:00–{busy[0] + 1:02d}:00</b> "
               + (f"({plural_leads(busy[1][0])})" if ru else f"({busy[1][0]} lid)"))
    if worst[1][1]:
        out.append(("Больше всего задержек: " if ru else "Eng ko'p zaderjka: ")
                   + f"<b>{worst[0]:02d}:00–{worst[0] + 1:02d}:00</b> ({worst[1][1]})")
    return out


# ═════════════════════════ 💤 qotib qolgan
def stale(db, tr, now: int, days: int) -> dict[int, list[dict]]:
    """Qotib qolgan lid: oxirgi N kun ichida na mijoz, na xodim yozmagan (Push hisobga kirmaydi), lekin oxirgi 30 kun
    ichida gaplashilgan. ⚡/💊 va stavkadagilar kirmaydi. -> {papka: [lid, ...]} (kartagacha yetganlar tepada)."""
    skip = skip_list(db)
    cards = _cards_by_thread(db)
    hi, lo = now - days * DAY, now - STALE_FLOOR_DAYS * DAY
    out: dict[int, list] = {}
    for th in db.all("SELECT chat_id, topic_id, last_seen, last_staff_ts, seen_msg_id, stavka FROM threads "
                     "WHERE first_seen IS NOT NULL"):
        fid = tr.chat_folder.get(th["chat_id"])
        talk = max(th["last_seen"] or 0, th["last_staff_ts"] or 0)
        if fid is None or th["stavka"] == "on" or not lo <= talk <= hi \
                or _excluded(tr, th["chat_id"], th["topic_id"], skip):
            continue
        c = cards.get((th["chat_id"], th["topic_id"]))
        out.setdefault(fid, []).append({
            "chat_id": th["chat_id"], "topic_id": th["topic_id"], "silent": now - talk, "cards": c["n"] if c else 0,
            "unanswered": (th["last_seen"] or 0) > (th["last_staff_ts"] or 0),
            "link": lead_link(th["chat_id"], th["topic_id"], th["seen_msg_id"])})
    for items in out.values():
        items.sort(key=lambda x: (-x["cards"], x["silent"]))
    return out


def stale_line(x: dict, lang: str) -> str:
    mark = "💳 " if x["cards"] else ""
    tail = f" · {dur(x['silent'], lang)}"
    if x["unanswered"]:
        tail += " · ❗ " + ("ждёт ответа" if lang == "ru" else "javobsiz")
    return f"{mark}{esc(x['link'])}{tail}"


# ═════════════════════════ 📉 soviyotgan
def cooling(db, tr, now: int, days: int) -> dict[int, list[dict]]:
    """Soviyotgan lid: xodim yozgan, mijoz odatdagidan 3 barobar (va kamida 1 soat) uzoq jim. Vaqt ish vaqtida
    hisoblanadi (tun kirmaydi). Mijozning kamida 2 ta javobi bo'lsa — «odatda» ma'lum. N kundan keyin — «qotib qolgan»."""
    skip = skip_list(db)
    cards = _cards_by_thread(db)
    ws, we = tr.work_window()
    out: dict[int, list] = {}
    for th in db.all("SELECT chat_id, topic_id, cl_turn, cl_avg, cl_n, cool_noted, seen_msg_id, stavka FROM threads "
                     "WHERE cl_turn IS NOT NULL AND cl_n>=2"):
        fid = tr.chat_folder.get(th["chat_id"])
        if fid is None or th["stavka"] == "on" or now - th["cl_turn"] >= days * DAY \
                or _excluded(tr, th["chat_id"], th["topic_id"], skip):
            continue
        usual = max(1, th["cl_avg"] or 0)
        silent = work_seconds(th["cl_turn"], now, tr.tz, ws, we)
        if silent < max(COOL_FACTOR * usual, COOL_MIN):
            continue
        c = cards.get((th["chat_id"], th["topic_id"]))
        out.setdefault(fid, []).append({
            "chat_id": th["chat_id"], "topic_id": th["topic_id"], "usual": usual, "silent": silent,
            "cards": c["n"] if c else 0, "link": lead_link(th["chat_id"], th["topic_id"], th["seen_msg_id"]),
            "turn": th["cl_turn"], "noted": th["cool_noted"]})
    for items in out.values():
        items.sort(key=lambda x: (-x["cards"], -x["silent"] / x["usual"]))
    return out


def cooling_line(x: dict, lang: str) -> str:
    mark = "💳 " if x["cards"] else ""
    if lang == "ru":
        return f"{mark}{esc(x['link'])} · обычно {dur(x['usual'], lang)} → молчит {dur(x['silent'], lang)}"
    return f"{mark}{esc(x['link'])} · odatda {dur(x['usual'], lang)} → {dur(x['silent'], lang)} jim"


def group_messages(db, kind: str, data: dict[int, list], days: int) -> list[str]:
    """«Проёб» uchun: HAR RD alohida xabar (aralashmaydi), ruscha, ixcham."""
    out = []
    for f in P.folders(db):
        items = data.get(f["id"]) or []
        if not items:
            continue
        what = (f"без движения {days}+ дн." if kind == "stale" else "остывают")
        lines = [small(f"{esc(f['name'])} · {what} · {len(items)}")]
        lines += [(stale_line if kind == "stale" else cooling_line)(x, "ru") for x in items[:GROUP_LIMIT]]
        if len(items) > GROUP_LIMIT:
            lines.append(small(f"… и ещё {len(items) - GROUP_LIMIT}"))
        lines.append(tag(P.folder_people(db, f["id"])))
        out.append("\n".join(lines))
    return out


async def cooling_alerts(ctx, now: int) -> int:
    """📉 Yangi soviyotgan lidlar — «Проёб»ga o'zi: HAR RD alohida xabar, papka xodimi belgilanadi. Har lid bir
    «navbat»da bir marta (mijoz javob qaytarib, yana jim bo'lsa — yana). Faqat ish vaqtida. -> nechta xabar."""
    from .timeutil import is_work_time
    db, tr = ctx.db, ctx.tracker
    if not (db.flag("an_cooling") and db.flag("cool_auto") and db.flag("bot_enabled")) \
            or not db.get("proyob_group_id"):
        return 0
    ws, we = tr.work_window()
    if not is_work_time(now, tr.tz, ws, we):
        return 0
    days = max(1, db.get_int("cooling_days", 2))
    data = cooling(db, tr, now, days)
    sent = 0
    for f in P.folders(db):
        fresh = [x for x in data.get(f["id"]) or [] if x["noted"] != x["turn"]]
        if not fresh:
            continue
        lines = [small(f"{esc(f['name'])} · остывают · {len(fresh)}")]
        lines += [cooling_line(x, "ru") for x in fresh[:GROUP_LIMIT]]
        if len(fresh) > GROUP_LIMIT:
            lines.append(small(f"… и ещё {len(fresh) - GROUP_LIMIT}"))
        lines.append(tag(P.folder_people(db, f["id"]), "напишите им, пока не остыли"))
        try:
            await ctx.notifier.send_group("\n".join(lines))
        except Exception:
            continue
        for x in fresh:
            db.run("UPDATE threads SET cool_noted=? WHERE chat_id=? AND topic_id=?", (x["turn"], x["chat_id"],
                                                                                   x["topic_id"]))
        sent += 1
    return sent


# ═════════════════════════ ⚡ javob tezligi → karta
def speed_outcome(db, tr, now: int) -> dict:
    """Oxirgi 30 kunda kelgan lidlar (yangi versiyadan keyin, kamida 3 kun oldin — natijasi aniq bo'lishi uchun):
    lidga o'rtacha javob tezligi (ish vaqtida, kartagacha) bo'yicha guruh va ulardan nechtasi 3 kun ichida karta oldi.
    -> {"rows": [(label, leads, carded)], "none": (leads, carded), "total": n}"""
    lo = max(since_ts(db), now - WIN_DAYS * DAY)
    hi = now - SPEED_WINDOW
    leads = [r for r in db.all("SELECT chat_id, topic_id, first_seen FROM threads WHERE first_seen>=? AND first_seen<=?",
                               (lo, hi)) if tr.chat_folder.get(r["chat_id"]) is not None]
    first_card: dict = {}
    for r in db.all("SELECT chat_id, topic_id, ts FROM cards WHERE ts>=? ORDER BY ts", (lo,)):
        first_card.setdefault((r["chat_id"], r["topic_id"]), []).append(r["ts"])
    reps: dict = {}
    for r in db.all("SELECT chat_id, topic_id, wait_since, reply_ts, work_seconds FROM replies WHERE wait_since>=?", (lo,)):
        reps.setdefault((r["chat_id"], r["topic_id"]), []).append(r)
    buckets = {lab: [0, 0] for _lim, lab in SPEED_BUCKETS}
    none = [0, 0]
    for ld in leads:
        key = (ld["chat_id"], ld["topic_id"])
        start, limit = ld["first_seen"], ld["first_seen"] + SPEED_WINDOW
        card = next((ts for ts in first_card.get(key, []) if start <= ts <= limit), None)
        end = card if card is not None else limit
        secs = [x["work_seconds"] for x in reps.get(key, []) if x["wait_since"] >= start and x["reply_ts"] <= end]
        slot = none
        if secs:
            avg = sum(secs) / len(secs)
            lab = next(lab for lim, lab in SPEED_BUCKETS if lim is None or avg <= lim)
            slot = buckets[lab]
        slot[0] += 1
        slot[1] += 1 if card is not None else 0
    return {"rows": [(lab, *buckets[lab]) for _lim, lab in SPEED_BUCKETS], "none": tuple(none), "total": len(leads)}


# ═════════════════════════ 🏆 g'oliblar
def winners(db, tr, now: int) -> dict:
    """Har xodim (oxirgi 30 kun, yangi versiyadan keyin): nechta lid bilan ishladi (javob bergan yoki karta yuborgan),
    nechtasiga karta yubordi, javob tezligi (ish vaqtida, mediana), lid birinchi yozgandan kartagacha (mediana).
    Papka akkauntidan yozilgan va papkada bir nechta xodim bo'lsa — «aniqlanmagan» (taxmin qilinmaydi)."""
    lo = max(since_ts(db), now - WIN_DAYS * DAY)
    first_seen = {(r["chat_id"], r["topic_id"]): r["first_seen"]
                  for r in db.all("SELECT chat_id, topic_id, first_seen FROM threads WHERE first_seen IS NOT NULL")}
    stat: dict = {}

    def slot(pid):
        return stat.setdefault(pid, {"leads": set(), "carded": set(), "reply": [], "to_card": {}})

    for r in db.all("SELECT chat_id, topic_id, person_id, work_seconds FROM replies WHERE reply_ts>=?", (lo,)):
        s = slot(r["person_id"])
        s["leads"].add((r["chat_id"], r["topic_id"]))
        s["reply"].append(r["work_seconds"])
    for r in db.all("SELECT chat_id, topic_id, person_id, ts FROM cards WHERE ts>=? ORDER BY ts", (lo,)):
        key = (r["chat_id"], r["topic_id"])
        s = slot(r["person_id"])
        s["leads"].add(key)
        s["carded"].add(key)
        fs = first_seen.get(key)
        if fs is not None and fs >= since_ts(db) and r["ts"] >= fs and key not in s["to_card"]:
            s["to_card"][key] = r["ts"] - fs
    people = {p["id"]: p for p in db.all("SELECT * FROM people")}
    rows = []
    for pid, s in stat.items():
        if pid is None or pid not in people:
            continue
        rows.append({"p": people[pid], "leads": len(s["leads"]), "cards": len(s["carded"]),
                     "reply": statistics.median(s["reply"]) if s["reply"] else None,
                     "to_card": statistics.median(s["to_card"].values()) if s["to_card"] else None,
                     "_reply": s["reply"], "_to_card": list(s["to_card"].values())})
    rows.sort(key=lambda x: (-(x["cards"] / x["leads"] if x["leads"] else 0), -x["leads"]))
    un = stat.get(None)
    unknown = {"replies": len(un["reply"]), "cards": len(un["carded"])} if un else None
    formula = None
    good = [x for x in rows if x["leads"] >= MIN_LEADS]
    if len(good) >= 2:
        k = max(1, len(good) // 3)
        best, rest = good[:k], good[k:]

        def med(xs, key):
            vals = [v for x in xs for v in x[key]]
            return statistics.median(vals) if vals else None
        formula = {"best": [x["p"]["name"] for x in best],
                   "best_conv": sum(x["cards"] for x in best) / max(1, sum(x["leads"] for x in best)),
                   "rest_conv": sum(x["cards"] for x in rest) / max(1, sum(x["leads"] for x in rest)),
                   "best_reply": med(best, "_reply"), "rest_reply": med(rest, "_reply"),
                   "best_card": med(best, "_to_card"), "rest_card": med(rest, "_to_card")}
    return {"rows": rows, "unknown": unknown, "formula": formula}


# ═════════════════════════ 📣 Push natijasi
def push_stats(db, now: int, limit: int = 10) -> list[dict]:
    """Har Push: nechta lidga ketdi, nechtasi keyin yozdi (90 daqiqa ichida), nechtasiga karta ketdi (24 soat ichida).
    Bitta lidga ketma-ket Push bo'lsa — natija OXIRGI Push'ga yoziladi. Oyna yopilmagan bo'lsa — «⏳»."""
    win = max(1, db.get_int("push_reply_min", 90)) * 60
    out = []
    for b in db.all("SELECT b.*, COUNT(p.bid) n, COUNT(p.replied_ts) rep, COUNT(p.card_ts) card FROM broadcasts b "
                    "LEFT JOIN push_log p ON p.bid=b.id GROUP BY b.id ORDER BY b.id DESC LIMIT ?", (limit,)):
        end = b["finished_ts"] or now
        out.append({"b": b, "n": b["n"], "rep": b["rep"], "card": b["card"],
                    "rep_open": b["status"] == "running" or now < end + win,
                    "card_open": b["status"] == "running" or now < end + CARD_WINDOW})
    return out


def push_by_folder(db, bid: int) -> list[tuple]:
    return [(r["folder_id"], r["n"], r["rep"], r["card"]) for r in db.all(
        "SELECT folder_id, COUNT(*) n, COUNT(replied_ts) rep, COUNT(card_ts) card FROM push_log WHERE bid=? "
        "GROUP BY folder_id ORDER BY n DESC", (bid,))]


# ═════════════════════════ 💳 kartalar
def cards_report(db, tr, s_ts: int, e_ts: int) -> dict[int, dict]:
    """Davrda har RD: necha marta karta yuborildi, nechta lidga; har lid — necha marta va oxirgisiga havola."""
    out: dict[int, dict] = {}
    for r in db.all("SELECT chat_id, topic_id, folder_id, COUNT(*) n, MAX(ts) last, MAX(msg_id) mid FROM cards "
                    "WHERE ts>=? AND ts<? GROUP BY chat_id, topic_id", (s_ts, e_ts)):
        fid = r["folder_id"] if r["folder_id"] is not None else tr.chat_folder.get(r["chat_id"])
        d = out.setdefault(fid, {"total": 0, "leads": []})
        d["total"] += r["n"]
        d["leads"].append({"n": r["n"], "last": r["last"], "link": lead_link(r["chat_id"], r["topic_id"], r["mid"])})
    for d in out.values():
        d["leads"].sort(key=lambda x: (-x["n"], -x["last"]))
    return out


def period(now: int, tz, key: str) -> tuple[int, int]:
    """td — bugun, yd — kecha, 7d — oxirgi 7 kun (bugun bilan)."""
    d0 = day_start(now, tz)
    if key == "yd":
        return d0 - DAY, d0
    if key == "7d":
        return d0 - 6 * DAY, now + 1
    return d0, now + 1
