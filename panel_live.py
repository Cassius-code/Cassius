"""👥 Hozir ishda — jonli xodimlar paneli (egasi bilan kelishilgan, 2026-10-30).

Bosh menyudagi tugma, har ~3 soniyada o'z joyida yangilanadi. Har xodim (📅 Bugun kim qayerda bo'yicha):
holati (🟢 ishda · ☕ tanaffusda · ⚪ hali kelmagan · 🛌 dam olishda), RD sida nechta lid javob kutyapti (🔴 — zaderjka),
lidga oxirgi marta qachon yozgan va bugun nechta «задержка» bo'lgan. Matn o'qilmaydi — faqat vaqt va kim."""
from __future__ import annotations

from . import people as P
from . import roster as R
from . import ui
from .attendance import break_until
from .timeutil import day_start, fmt, local_date
from .ui import Req, card, h, kb, nav, screen, title


def ago(r: Req, seconds: int) -> str:
    m = max(0, int(seconds)) // 60
    if m < 1:
        return r.L("hozirgina", "только что")
    if m < 60:
        return r.L(f"{m} daq oldin", f"{m} мин назад")
    return r.L(f"{m // 60} soat {m % 60:02d} daq oldin", f"{m // 60} ч {m % 60:02d} мин назад")


def person_line(ctx, r: Req, p, rds: list, lc: dict, now: int, d0: int) -> str:
    db, day = ctx.db, local_date(now, ctx.tz)
    if not rds:
        return f"🛌 <b>{h(P.mention(p))}</b> — {r.L('dam olishda', 'выходной')}"
    row = db.one("SELECT arrived_ts, last_act_ts FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), p["id"]))
    until = break_until(db, p["id"], now)
    if until:
        hm = fmt(until, ctx.tz, "%H:%M")
        icon, state = "☕", r.L(f"tanaffus {hm} gacha", f"перерыв до {hm}")
    elif row is not None and row["arrived_ts"]:
        icon, state = "🟢", r.L("ishda", "на работе")
    else:
        icon, state = "⚪", r.L("hali kelmagan", "ещё не пришёл")
    names = ", ".join(h(f["name"]) for f in rds)
    wait = sum(lc["wait_by"].get(f["id"], 0) for f in rds)
    red = sum(lc["overdue"].get(f["id"], 0) for f in rds)
    waits = r.L(f"⏱ kutyapti {wait}", f"⏱ ждут {wait}") + (f" (🔴 {red})" if red else "")
    # faqat lidga yozgani («Проёб»dagi xabari emas): o'z akkauntidan — jurnal, papka akkauntidan — shu ishga tushgandan beri
    own = db.scalar("SELECT MAX(ts) FROM journal WHERE who='staff' AND sender_id=? AND ts>=?", (p["tg_id"], d0)) \
        if p["tg_id"] else 0
    last = max(int(own or 0), ctx.att._work_ts.get(p["id"], 0))
    seen = ago(r, now - last) if last >= d0 else "—"
    q = ",".join("?" * len(rds))
    delays = db.scalar(f"SELECT COUNT(DISTINCT group_msg_id) FROM alerts WHERE created_ts>=? AND status<>'void' "
                       f"AND group_msg_id IS NOT NULL AND folder_id IN ({q})", [d0] + [f["id"] for f in rds])
    return f"{icon} <b>{h(P.mention(p))}</b> · {names}\n   {state} · {waits} · ✍️ {seen} · 🚨 {delays}"


@screen("lv", "view")
async def live_staff(ctx, r: Req):
    ui.view(r, "lv")                                       # jonli yangilanadi (panel.live_refresh)
    db, now = ctx.db, int(ctx.clock())
    day, d0 = local_date(now, ctx.tz), day_start(now, ctx.tz)
    lc = ctx.tracker.live_counts(now)
    lines = []
    for p in ctx.att.tracked():
        rds = R.person_rds(db, p["id"], day)
        lines.append(person_line(ctx, r, p, rds, lc, now, d0))
    lines.sort(key=lambda x: x.startswith("🛌"))
    legend = r.L("<i>🟢 ishda · ☕ tanaffus · ⚪ hali kelmagan · 🛌 dam olishda · ⏱ javob kutayotgan lidlar (🔴 zaderjka) · "
                 "✍️ lidga oxirgi yozgani · 🚨 bugungi zaderjkalar</i>",
                 "<i>🟢 на работе · ☕ перерыв · ⚪ ещё не пришёл · 🛌 выходной · ⏱ ждут ответа (🔴 задержка) · "
                 "✍️ последнее сообщение лиду · 🚨 задержки за сегодня</i>")
    body = card(["\n".join(lines)]) if lines else r.L("<i>Bugun ishlaydigan xodim yo'q.</i>",
                                                       "<i>Сегодня работающих сотрудников нет.</i>")
    return ui.join(title("👥", r.L("HOZIR ISHDA", "СЕЙЧАС НА РАБОТЕ"), fmt(now, ctx.tz, "%H:%M:%S")), "", body,
                   legend), kb(nav(r))
