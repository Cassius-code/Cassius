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
    rows = grid(opts)
    if r.can("full"):
        rows.append([(r.L("📈 Tahlil: soatlar, lidlar, kartalar", "📈 Аналитика: часы, лиды, карты"), "an")])
    return ui.join(title("📊", r.L("HISOBOTLAR", "ОТЧЁТЫ")), "",
                   ui.card([r.L("Zaderjkalar, javob tezligi, ishga kelish va kassa — bitta joyda.",
                                "Задержки, скорость ответа, приход и касса — в одном месте.")])), \
        kb(*rows, nav(r))
