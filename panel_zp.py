"""💵 «Faqat zp» admini: jami kassa va jami zp, har xodim — kassa, $ va zp (bonus/jarima bilan), kunma-kun cheklar va
o'tgan haftalar. Foizlar, PDF, o'zgartirish, egasining va Arturning ulushi — YO'Q (egasi bilan kelishilgan)."""
from __future__ import annotations

import datetime as dt

from . import kassa as K
from . import people as P
from . import ui
from .kassa_view import adj_lines, label, money, num
from .timeutil import local_date
from .ui import Req, card, grid, h, kb, screen, title

SHOW = ("worker", "pool")          # egasi (self) va hamkor (partner) — ko'rinmaydi


def _today(ctx) -> dt.date:
    return local_date(ctx.clock(), ctx.tz)


def _period(ctx, key: str | None) -> tuple[dt.date, dt.date, str]:
    t = _today(ctx)
    key = key or "tw"
    try:
        s, e = K.period_range(key, t)
    except Exception:
        key = "tw"
        s, e = K.period_range(key, t)
    return s, e, key


def _weeks(ctx, n: int = 6) -> list[tuple[str, str]]:
    """O'tgan haftalar: (tugma matni, kalit)."""
    mon = K.week_start(_today(ctx))
    out = []
    for i in range(2, n + 2):
        s = mon - dt.timedelta(days=7 * i)
        e = s + dt.timedelta(days=6)
        out.append((label(s, e), f"{s.isoformat()}_{e.isoformat()}"))
    return out


@screen("zh", "zp")
async def zp_home(ctx, r: Req):
    db = ctx.db
    s, e, key = _period(ctx, r.args[0] if r.args else None)
    ui.view(r, f"zh:{key}")
    b = K.calc(db, s, e)
    ready = K.zp_state(db, s, e, _today(ctx))["ready"]
    rows = [b["rows"][i] for i in b["order"] if i in b["rows"] and b["rows"][i]["kind"] in SHOW and K.has_data(b["rows"][i])]
    zp_total = sum(x["total"] or 0 for x in rows if x["kind"] == "worker" and x["total"] is not None)
    est = "" if ready else r.L(" ≈ <i>(taxminiy — 🧮 hafta hali hisoblanmagan)</i>",
                               " ≈ <i>(примерно — 🧮 неделя ещё не рассчитана)</i>")
    head = [r.L(f"💵 Jami kassa: <b>{num(b['raw'])}</b> · <b>{money(b['K'])} $</b>",
                f"💵 Общая касса: <b>{num(b['raw'])}</b> · <b>{money(b['K'])} $</b>"),
            r.L(f"💰 Jami zp: <b>{money(zp_total)} $</b>", f"💰 Общая зп: <b>{money(zp_total)} $</b>") + est]
    lines, btn = [], []
    for x in rows:
        bits = [f"{num(x['raw'])}", f"{money(x['usd'])} $"] if x["n"] else []
        if x["kind"] == "worker" and x["total"] is not None:
            bits.append(r.L(f"zp <b>{money(x['total'])} $</b>", f"зп <b>{money(x['total'])} $</b>"))
        extra = []
        if x["bonus"]:
            extra.append(f"+{money(x['bonus'])}")
        if x["fine"]:
            extra.append(f"−{money(x['fine'])}")
        tag = r.L(" (umumiy)", " (общий)") if x["kind"] == "pool" else ""
        lines.append(f"<b>{h(x['p']['name'])}</b>{tag} — " + " · ".join(bits) + (f" <i>({' '.join(extra)})</i>"
                                                                                 if extra else ""))
        btn.append((x["p"]["name"][:24], f"zp:{x['p']['id']}:{key}"))
    body = card(lines) if lines else r.L("<i>Bu davrda ma'lumot yo'q.</i>", "<i>За период данных нет.</i>")
    rows_kb = grid(btn)
    rows_kb.append([(("✅ " if key == "tw" else "") + r.L("Bu hafta", "Эта неделя"), "zh:tw"),
                    (("✅ " if key == "lw" else "") + r.L("O'tgan hafta", "Прошлая неделя"), "zh:lw")])
    rows_kb += grid([(("✅ " if key == k else "") + t, f"zh:{k}") for t, k in _weeks(ctx, 4)], 2)
    rows_kb.append([(r.L("📅 Bu oy", "📅 Этот месяц"), "zh:tm"), (r.L("📅 O'tgan oy", "📅 Прошлый месяц"), "zh:lm")])
    return ui.join(title("💵", r.L("ZP", "ЗП"), label(s, e)), "", card(head), body,
                   r.L("<i>Xodimni bosing — kunma-kun cheklar va zp.</i>",
                       "<i>Нажмите сотрудника — чеки по дням и зп.</i>")), kb(*rows_kb)


@screen("zp", "zp")
async def zp_person(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = ui.must(P.person(db, pid))
    if p["kassa_kind"] not in SHOW:
        raise ui.Gone()
    s, e, key = _period(ctx, r.args[1] if len(r.args) > 1 else None)
    b = K.calc(db, s, e)
    x = b["rows"].get(pid)
    ready = K.zp_state(db, s, e, _today(ctx))["ready"]
    parts = [title("💵", h(p["name"]), label(s, e)), ""]
    if x is None or not K.has_data(x):
        parts.append(r.L("<i>Bu davrda ma'lumot yo'q.</i>", "<i>За период данных нет.</i>"))
    else:
        parts.append(card([r.L(f"Kassa: <b>{num(x['raw'])}</b>", f"Касса: <b>{num(x['raw'])}</b>"),
                           r.L(f"Cheklar (Кол-во рд): <b>{x['n']}</b>", f"Кол-во рд: <b>{x['n']}</b>"),
                           r.L(f"Kassa ($): <b>{money(x['usd'])} $</b>", f"Касса ($): <b>{money(x['usd'])} $</b>")]))
        days = []
        for d, dd in x["days"].items():
            days.append(f"{d[8:10]}.{d[5:7]} — " + ", ".join(num(a) for a, _u in dd["items"]) +
                        f" · <b>{num(dd['raw'])}</b> · {money(dd['usd'])} $" +
                        (f" <i>→ {h(', '.join(dd['ops']))}</i>" if dd["ops"] else ""))
        if days:
            parts.append(card([f"<b>{r.L('Kunma-kun', 'По дням')}</b>"] + days))
        zl = []
        if x["kind"] == "worker" and x["zp_on"]:
            zl.append(r.L(f"Zp: <b>{money(x['zp'])} $</b>", f"Зп: <b>{money(x['zp'])} $</b>"))
        zl += adj_lines(x, r.lang)
        if x["total"] is not None and x["kind"] == "worker":
            zl.append(f"= <b>{money(x['total'])} $</b>")
        if zl:
            est = "" if ready else r.L(" · <i>≈ taxminiy</i>", " · <i>≈ примерно</i>")
            parts.append(card([f"<b>💰 {r.L('Zp', 'Зп')}</b>{est}"] + zl))
    rows_kb = [[(("✅ " if key == "tw" else "") + r.L("Bu hafta", "Эта неделя"), f"zp:{pid}:tw"),
                (("✅ " if key == "lw" else "") + r.L("O'tgan hafta", "Прошлая неделя"), f"zp:{pid}:lw")]]
    rows_kb += grid([(("✅ " if key == k else "") + t, f"zp:{pid}:{k}") for t, k in _weeks(ctx, 4)], 2)
    rows_kb.append([(r.L("‹ Orqaga", "‹ Назад"), ui.back_data(f"zh:{key}")), (r.L("⌂ Menyu", "⌂ Меню"), "m")])
    return ui.join(*parts), kb(*rows_kb)
