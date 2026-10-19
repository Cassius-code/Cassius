"""Hisobotlar: kunlik/haftalik/oylik (panel va avtomat), «Проёб» guruhiga haftalik qisqa xulosa (ruscha)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from . import kassa as K
from . import people as P
from .kassa_view import h, money, num
from .timeutil import at, local_date, minutes_up


def bounds(s: dt.date, e: dt.date, tz: ZoneInfo) -> tuple[int, int]:
    return at(s, dt.time(0, 0), tz), at(e + dt.timedelta(days=1), dt.time(0, 0), tz)


def label(s: dt.date, e: dt.date) -> str:
    return s.strftime("%d.%m") if s == e else f"{s:%d.%m} – {e:%d.%m}"


def staff_stats(db, s_ts: int, e_ts: int, tz: ZoneInfo) -> list[dict]:
    """Xodim bo'yicha: javoblar, o'rtacha/eng uzun kutish (ish vaqti), zaderjkalar, jarima $."""
    out: dict[int, dict] = {}
    names = {}
    for r in db.all("SELECT staff_id, COUNT(*) n, AVG(work_seconds) avg_s, MAX(work_seconds) max_s FROM replies "
                    "WHERE reply_ts>=? AND reply_ts<? GROUP BY staff_id", (s_ts, e_ts)):
        uid = r["staff_id"]
        p = P.by_tg(db, uid) if uid else None
        key = p["id"] if p else -(uid or 0)
        acc = db.one("SELECT name, label FROM accounts WHERE user_id=?", (uid,)) if uid and p is None else None
        names[key] = p["name"] if p else (
            (f"📲 {acc['name']}" if acc else "") or db.scalar("SELECT name FROM known_humans WHERE user_id=?", (uid,), "")
            or (str(uid) if uid else "—"))
        d = out.setdefault(key, {"n": 0, "avg": 0, "max": 0, "delays": 0, "fine": 0.0, "late": 0, "late_min": 0})
        d["n"] += r["n"]
        d["avg"], d["max"] = int(r["avg_s"] or 0), int(r["max_s"] or 0)
    s_day = dt.datetime.fromtimestamp(s_ts, tz).date().isoformat()
    e_day = dt.datetime.fromtimestamp(e_ts - 1, tz).date().isoformat()
    blank = {"n": 0, "avg": 0, "max": 0, "delays": 0, "fine": 0.0, "late": 0, "late_min": 0}
    for a in db.all("SELECT fp.person_id, COUNT(*) n FROM alerts a JOIN folder_people fp ON fp.folder_id=a.folder_id "
                    "WHERE a.created_ts>=? AND a.created_ts<? AND a.status<>'void' GROUP BY fp.person_id",
                    (s_ts, e_ts)):
        out.setdefault(a["person_id"], dict(blank))["delays"] = a["n"]
        names.setdefault(a["person_id"], (P.person(db, a["person_id"]) or {"name": "?"})["name"])
    for a in db.all("SELECT person_id, SUM(usd) s FROM adj WHERE source='delay' AND cancelled=0 "
                    "AND day BETWEEN ? AND ? GROUP BY person_id", (s_day, e_day)):
        out.setdefault(a["person_id"], dict(blank))["fine"] = float(a["s"] or 0)
        names.setdefault(a["person_id"], (P.person(db, a["person_id"]) or {"name": "?"})["name"])
    for a in db.all("SELECT person_id, COUNT(*) n, SUM(late_min) m FROM attendance WHERE late_min>0 AND day BETWEEN ? "
                    "AND ? GROUP BY person_id", (s_day, e_day)):
        d = out.setdefault(a["person_id"], dict(blank))
        d["late"], d["late_min"] = a["n"], int(a["m"] or 0)
        names.setdefault(a["person_id"], (P.person(db, a["person_id"]) or {"name": "?"})["name"])
    rows = [dict(v, name=names.get(k, "?"), key=k) for k, v in out.items()]
    rows.sort(key=lambda x: (x["delays"], x["late"], -x["n"]))
    return rows


def delays_by_folder(db, s_ts: int, e_ts: int) -> list[tuple[str, int]]:
    return [(r["name"], r["n"]) for r in db.all(
        "SELECT f.name, COUNT(*) n FROM alerts a JOIN folders f ON f.id=a.folder_id WHERE a.created_ts>=? "
        "AND a.created_ts<? AND a.status<>'void' GROUP BY f.id ORDER BY n DESC", (s_ts, e_ts))]


def new_leads(db, s_ts: int, e_ts: int) -> list[tuple[str, int]]:
    return [(r["name"], r["n"]) for r in db.all(
        "SELECT f.name, COUNT(*) n FROM threads t JOIN chats c ON c.chat_id=t.chat_id JOIN folders f ON f.id=c.folder_id "
        "WHERE t.first_seen>=? AND t.first_seen<? GROUP BY f.id ORDER BY n DESC", (s_ts, e_ts))]


def summary(ctx, s: dt.date, e: dt.date, lang: str, owner: bool, full: bool = True) -> str:
    """Panel va egaga avtomat hisobot (HTML, premium kartochkalar)."""
    db, tz = ctx.db, ctx.tz
    L = (lambda uz, ru: ru if lang == "ru" else uz)
    s_ts, e_ts = bounds(s, e, tz)
    parts = [f"<b>📊 {L('HISOBOT', 'ОТЧЁТ')}</b>", f"<i>{label(s, e)}</i>", ""]
    leads = new_leads(db, s_ts, e_ts)
    total_leads = sum(n for _, n in leads)
    dl = delays_by_folder(db, s_ts, e_ts)
    pushed = db.scalar("SELECT COALESCE(SUM(sent),0) FROM broadcasts WHERE started_ts>=? AND started_ts<?", (s_ts, e_ts))
    lines = [f"🆕 {L('Yangi lidlar', 'Новые лиды')} — <b>{total_leads}</b>"]
    lines += [f"   {h(n)} · {c}" for n, c in leads]
    lines.append(f"🚨 {L('Zaderjkalar', 'Задержки')} — <b>{sum(c for _, c in dl)}</b>"
                 + (f" ({', '.join(f'{h(n)} {c}' for n, c in dl)})" if dl else ""))
    inc = {r["status"]: r["n"] for r in db.all("SELECT status, COUNT(*) n FROM incidents WHERE started_ts>=? AND "
                                                "started_ts<? GROUP BY status", (s_ts, e_ts))}
    if inc:
        lines.append(f"⚠️ {L('Ko‘p lid javobsiz', 'Много лидов без ответа')} — <b>{sum(inc.values())}</b> "
                     f"({L('kechirildi', 'прощено')} {inc.get('warn', 0)} · {L('vaqtida javob', 'успели')} "
                     f"{inc.get('ok', 0)} · {L('jarima', 'штраф')} {inc.get('fined', 0)})")
    lines.append(f"📣 Push — <b>{pushed}</b>")
    parts.append("<blockquote>" + "\n".join(lines) + "</blockquote>")
    st = staff_stats(db, s_ts, e_ts, tz)
    if st:
        sl = [f"<b>👥 {L('Xodimlar', 'Сотрудники')}</b>"]
        for x in st:
            bits = [f"{x['n']} {L('javob', 'отв.')}"]
            if x["n"]:
                bits.append(f"⌀ {minutes_up(x['avg'])} {L('daq', 'мин')}")
            if x["delays"]:
                bits.append(f"🚨 {x['delays']}")
            if x["fine"] and full:
                bits.append(f"💸 {money(x['fine'])} $")
            if x["late"]:
                bits.append(f"🕘 {x['late']} ({x['late_min']} {L('daq', 'мин')})")
            sl.append(f"{h(x['name'])} — " + " · ".join(bits))
        parts.append("<blockquote>" + "\n".join(sl) + "</blockquote>")
    if s == e:
        att = ctx.att.day_summary(s)
        if att:
            came = [a for a in att if a["arrived"]]
            missing = [a for a in att if not a["arrived"] and not a["off"]]
            al = [f"<b>🙋 {L('Ishga kelish', 'Приход')}</b> — {len(came)} / {len([a for a in att if not a['off']])}"]
            for a in came:
                t = dt.datetime.fromtimestamp(a["arrived"], tz).strftime("%H:%M")
                al.append(f"{h(a['p']['name'])} {t}" + (f" · 🕘 {a['late']} {L('daq', 'мин')}" if a["late"] else ""))
            if missing:
                al.append(f"❌ {L('Kelmadi', 'Нет')}: " + ", ".join(h(a["p"]["name"]) for a in missing))
            parts.append("<blockquote>" + "\n".join(al) + "</blockquote>")
    if full:
        b = K.calc(db, s, e)
        kl = [f"<b>💵 {L('Kassa', 'Касса')}</b> — {num(b['n'])} {L('chek', 'чек.')} · <b>{money(b['K'])} $</b>"]
        if owner and K.zp_state(db, s, e, local_date(ctx.clock(), tz))["ready"]:
            kl.append(f"💼 {L('Daromadingiz', 'Ваш доход')} — <b>{money(b['owner']['income'])} $</b>")
        parts.append("<blockquote>" + "\n".join(kl) + "</blockquote>")
    return "\n".join(parts)


def weekly_group(ctx, s: dt.date, e: dt.date) -> str:
    """«Проёб» guruhiga (ruscha): hafta xulosasi va eng yaxshilar (🥇🥈🥉). Pul raqamlari yo'q.
    Reyting: kam zaderjka → kam kech qolish → tez javob → ko'p javob; medal uchun yetarli ish hajmi kerak."""
    db = ctx.db
    s_ts, e_ts = bounds(s, e, ctx.tz)
    st = staff_stats(db, s_ts, e_ts, ctx.tz)
    lines = [f"📅 Итоги недели {label(s, e)}", ""]
    if not st:
        lines.append("Данных пока нет.")
        return "\n".join(lines)
    top_n = max(x["n"] for x in st)
    enough = max(5, int(top_n * 0.2))

    def key(x):
        return (x["delays"], x["late"], x["avg"] if x["n"] else 10 ** 9, -x["n"])
    ranked = sorted([x for x in st if x["n"] >= enough], key=key)
    rest = sorted([x for x in st if x["n"] < enough], key=key)

    def row(x):
        bits = [f"ответов {x['n']}"]
        if x["n"]:
            bits.append(f"ср. {minutes_up(x['avg'])} мин")
        bits.append(f"задержек {x['delays']}" if x["delays"] else "без задержек ✅")
        if x["late"]:
            bits.append(f"опозданий {x['late']}")
        return f"{x['name']} — " + " · ".join(bits)
    medals = ["🥇", "🥈", "🥉"]
    if ranked:
        lines.append("🏆 Лучшие:")
        for i, x in enumerate(ranked[:3]):
            lines.append(f"{medals[i]} {row(x)}")
        if len(ranked) > 3 or rest:
            lines += ["", "Остальные:"]
        for i, x in enumerate(ranked[3:], 4):
            lines.append(f"{i}. {row(x)}")
    for x in rest:
        lines.append(f"• {row(x)}")
    return "\n".join(lines)
