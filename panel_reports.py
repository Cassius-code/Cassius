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
    rows.append([(r.L("📊 Lid bazasi (har RD)", "📊 База лидов (по RD)"), "rb")])
    if r.can("full"):
        rows.append([(r.L("📈 Tahlil: soatlar, lidlar, kartalar", "📈 Аналитика: часы, лиды, карты"), "an")])
    if r.owner:
        rows.append([(r.L("📈 G'ayrioddiy o'zgarish", "📈 Необычные изменения"), "ana:lw")])
    return ui.join(title("📊", r.L("HISOBOTLAR", "ОТЧЁТЫ")), "",
                   ui.card([r.L("Zaderjkalar, javob tezligi, ishga kelish va kassa — bitta joyda.",
                                "Задержки, скорость ответа, приход и касса — в одном месте.")])), \
        kb(*rows, nav(r))


@screen("ana", "owner")
async def anomalies(ctx, r: Req):
    """📈 G'ayrioddiy o'zgarish: tanlangan hafta oldingi 3 haftaning o'rtachasiga nisbatan (faqat raqamlar)."""
    import datetime as dt

    from .anomaly import changes
    from .kassa_view import label
    t = local_date(ctx.clock(), ctx.tz)
    key = r.args[0] if r.args and r.args[0] in ("tw", "lw") else "lw"
    mon = K.week_start(t) - (dt.timedelta(days=7) if key == "lw" else dt.timedelta(0))
    lines = changes(ctx.db, mon, ctx.tz, r.lang)
    body = ui.card([ui.h(x) for x in lines]) if lines else r.L("<i>Hammasi odatdagidek — keskin o'zgarish yo'q 👍</i>",
                                                              "<i>Всё как обычно — резких изменений нет 👍</i>")
    sub = label(mon, mon + dt.timedelta(days=6)) + (r.L(" (hali tugamagan)", " (ещё идёт)") if key == "tw" else "")
    note = r.L("Solishtirish — oldingi 3 haftaning o'rtachasi bilan. Kichik raqamlar (tasodif) chiqmaydi; farq ±35% "
               "va undan katta bo'lsa ko'rinadi. Har dushanba 09:00 da o'tgan hafta bo'yicha o'zi keladi.",
               "Сравнение — со средним за 3 предыдущие недели. Мелкие числа (случайность) не показываются; видно, если "
               "разница ±35% и больше. Каждый понедельник в 09:00 приходит само за прошлую неделю.")
    other = [(r.L("🗓 Shu hafta", "🗓 Эта неделя"), "ana:tw")] if key == "lw" else \
        [(r.L("🗓 O'tgan hafta", "🗓 Прошлая неделя"), "ana:lw")]
    return ui.join(title("📈", r.L("G'AYRIODDIY O'ZGARISH", "НЕОБЫЧНЫЕ ИЗМЕНЕНИЯ"), sub), "", body, f"<i>{note}</i>"), \
        kb(other, nav(r, "r"))


# ───────────────────────── 📊 lid bazasi holati (egasi bilan kelishilgan, 2026-10-30)
def base_stats(ctx, now: int) -> dict[int, dict]:
    """Har RD: jami va yangi (bugun / shu hafta), faol va jim (bugun / 7 kun / qotib qolgan / soviyotgan),
    holatlar (javob kutyapti / stavkada / ⚡💊 chiqarilgan). Matn o'qilmaydi — faqat vaqt va kim."""
    from . import insights as I
    from . import people as P
    from .panel_control import folder_leads
    from .reports import new_leads_in
    from .rules import label_excluded, skip_list
    from .timeutil import day_start
    db, tr = ctx.db, ctx.tracker
    t = local_date(now, ctx.tz)
    week0 = day_start(now, ctx.tz) - t.weekday() * 86400
    lc = tr.live_counts(now)
    stale = I.stale(db, tr, now, max(1, db.get_int("stale_days", 3)))
    cool = I.cooling(db, tr, now, max(1, db.get_int("cooling_days", 2)))
    skip = skip_list(db)
    out = {}
    for f in P.folders(db):
        fid = f["id"]
        excluded = sum(1 for x in db.all("SELECT t.icon, t.title FROM topics t JOIN chats c ON c.chat_id=t.chat_id "
                                         "WHERE c.folder_id=? AND t.topic_id>1", (fid,))
                       if label_excluded(f"{x['icon']} {x['title']}", skip))
        stavka = db.scalar("SELECT COUNT(*) FROM threads th JOIN chats c ON c.chat_id=th.chat_id "
                           "WHERE c.folder_id=? AND th.stavka='on'", (fid,))
        out[fid] = dict(folder_leads(ctx, fid), f=f, new_week=new_leads_in(db, fid, week0, now + 1),
                        stale=len(stale.get(fid, [])), cool=len(cool.get(fid, [])), wait=lc["wait_by"].get(fid, 0),
                        red=lc["overdue"].get(fid, 0), stavka=stavka, excluded=excluded)
    return out


def base_lines(r: Req, x: dict, stale_days: int) -> list[str]:
    red = f" (🔴 {x['red']})" if x["red"] else ""
    return [r.L(f"📦 Jami <b>{x['all']}</b> · 🆕 bugun <b>{x['new']}</b> · shu hafta <b>{x['new_week']}</b>",
                f"📦 Всего <b>{x['all']}</b> · 🆕 сегодня <b>{x['new']}</b> · за неделю <b>{x['new_week']}</b>"),
            r.L(f"💬 bugun yozgan <b>{x['today']}</b> · 7 kunda <b>{x['week']}</b> · 💤 {stale_days}+ kun jim "
                f"<b>{x['stale']}</b> · 📉 soviyotgan <b>{x['cool']}</b>",
                f"💬 писали сегодня <b>{x['today']}</b> · за 7 дней <b>{x['week']}</b> · 💤 молчат {stale_days}+ дн. "
                f"<b>{x['stale']}</b> · 📉 остывают <b>{x['cool']}</b>"),
            r.L(f"⏱ javob kutyapti <b>{x['wait']}</b>{red} · 🎬 stavkada <b>{x['stavka']}</b> · ⚡💊 <b>{x['excluded']}</b>",
                f"⏱ ждут ответа <b>{x['wait']}</b>{red} · 🎬 в ставке <b>{x['stavka']}</b> · ⚡💊 <b>{x['excluded']}</b>")]


@screen("rb", "view")
async def lead_base(ctx, r: Req):
    """📊 Har RD lid bazasi holati; RD bosilsa — batafsil (qotib qolgan va soviyotgan lidlar havolalari bilan)."""
    from . import insights as I
    from .ui import card, h
    now = int(ctx.clock())
    stats = base_stats(ctx, now)
    sd = max(1, ctx.db.get_int("stale_days", 3))
    from .panel_push import dstr
    base = dstr(ctx.db.get("push_base_from") or "2026-08-28")
    legend = r.L(f"<i>📦 Jami — {base} dan keyin o'zi yozgan lidlar. "
                 "Yangi — shu davrda ochilgan topiklar. 💤 qotib qolgan, 📉 soviyotgan — 📈 Tahlildagidek. "
                 "⚡💊 — chiqarilgan statusdagilar.</i>",
                 f"<i>📦 Всего — лиды, писавшие сами после {base}. "
                 "Новые — топики, открытые за период. 💤 застывшие, 📉 остывающие — как в 📈 Аналитике. "
                 "⚡💊 — исключённые статусы.</i>")
    if r.args and r.args[0].isdigit() and int(r.args[0]) in stats:
        fid = int(r.args[0])
        x = stats[fid]
        tr = ctx.tracker
        lines = base_lines(r, x, sd)
        st = I.stale(ctx.db, tr, now, sd).get(fid, [])[:10]
        co = I.cooling(ctx.db, tr, now, max(1, ctx.db.get_int("cooling_days", 2))).get(fid, [])[:10]
        parts = [title("📊", h(x["f"]["name"]), r.L("lid bazasi", "база лидов")), "", card(lines)]
        if st:
            parts.append(card([f"<b>💤 {r.L('Qotib qolgan', 'Застывшие')}</b>"] + [I.stale_line(y, r.lang) for y in st]))
        if co:
            parts.append(card([f"<b>📉 {r.L('Soviyotgan', 'Остывают')}</b>"] + [I.cooling_line(y, r.lang) for y in co]))
        return ui.join(*parts, legend), kb(nav(r, "rb"))
    blocks, btn = [], []
    for x in stats.values():
        blocks.append(f"<b>📁 {h(x['f']['name'])}</b>\n" + "\n".join(base_lines(r, x, sd)))
        btn.append((f"📁 {x['f']['name']}"[:30], f"rb:{x['f']['id']}"))
    body = card(["\n\n".join(blocks)]) if blocks else r.L("<i>Papka yo'q.</i>", "<i>Папок нет.</i>")
    return ui.join(title("📊", r.L("LID BAZASI", "БАЗА ЛИДОВ"), r.L("har RD", "по RD")), "", body, legend), \
        kb(*grid(btn, 3), nav(r, "r"))
