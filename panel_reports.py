"""📊 Hisobotlar: bugun / kecha / hafta / oy (zaderjka, javoblar, ishga kelish, kassa)."""
from __future__ import annotations

from . import kassa as K
from . import ui
from .reports import summary
from .timeutil import local_date
from .ui import Req, grid, kb, nav, screen, title


@screen("r", "view")
async def reports_menu(ctx, r: Req):
    if r.args:
        t = local_date(ctx.clock(), ctx.tz)
        s, e = K.period_range(r.args[0], t)
        text = summary(ctx, s, e, r.lang, r.owner, full=r.can("full"))
        others = [(lab, f"r:{k}") for lab, k in ((r.L("📅 Bugun", "📅 Сегодня"), "td"), (r.L("↩️ Kecha", "↩️ Вчера"), "yd"),
                                                  (r.L("🗓 Hafta", "🗓 Неделя"), "tw"),
                                                  (r.L("🗓 O'tgan hafta", "🗓 Прошлая"), "lw")) if k != r.args[0]]
        return text, kb(others, nav(r, "r"))
    opts = [(r.L("📅 Bugun", "📅 Сегодня"), "r:td"), (r.L("↩️ Kecha", "↩️ Вчера"), "r:yd"),
            (r.L("🗓 Shu hafta", "🗓 Эта неделя"), "r:tw"), (r.L("🗓 O'tgan hafta", "🗓 Прошлая неделя"), "r:lw"),
            (r.L("📆 Shu oy", "📆 Этот месяц"), "r:tm"), (r.L("📆 O'tgan oy", "📆 Прошлый месяц"), "r:lm")]
    text = ui.join(title("📊", r.L("HISOBOTLAR", "ОТЧЁТЫ")), "",
                   ui.card([r.L("Zaderjkalar, javob tezligi, ishga kelish va kassa — bitta joyda.",
                                "Задержки, скорость ответа, приход и касса — в одном месте.")]))
    return ui.rich(text, reports_card(ctx, r)), kb(*grid(opts), nav(r))


def reports_card(ctx, r: Req) -> list:
    import datetime as dt
    from . import panel_cards as PC
    from .kassa_view import num
    from .timeutil import day_start
    db, now = ctx.db, int(ctx.clock())
    t = dt.datetime.fromtimestamp(now, ctx.tz)
    d0 = day_start(now, ctx.tz)
    w0 = d0 - t.weekday() * 86400
    q = "SELECT COUNT(*) FROM alerts WHERE created_ts>=? AND status<>'void'"
    came = db.scalar("SELECT COUNT(*) FROM attendance WHERE day=? AND arrived_ts IS NOT NULL", (t.date().isoformat(),))
    kd = kw = None
    if r.can("full"):
        kd = num(K.calc(db, t.date(), t.date())["raw"])
        kw = num(K.calc(db, K.week_start(t.date()), t.date())["raw"])
    return PC.reports(r, t, db.scalar(q, (d0,)), db.scalar(q, (w0,)), came, len(ctx.att.staff()), kd, kw)
