"""📅 Bugun kim qayerda: har RD da shu kuni kim ishlaydi, kim dam oladi, bo'sh RD ga kim qaraydi.

Bitta RD — bitta xodim. Belgilash, jarima va eslatmalar shu ro'yxat bo'yicha (dam olayotgan belgilanmaydi)."""
from __future__ import annotations

import datetime as dt

from . import people as P
from . import roster as R
from . import ui
from .timeutil import local_date
from .ui import Req, card, grid, h, kb, nav, screen, title

DAYS_UZ = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def _day(ctx, r: Req, idx: int = 0) -> tuple[dt.date, int]:
    """args[idx] — 0 (bugun) yoki 1 (ertaga)."""
    off = 1 if len(r.args) > idx and r.args[idx] == "1" else 0
    return local_date(ctx.clock(), ctx.tz) + dt.timedelta(days=off), off


def _day_name(r: Req, d: dt.date, off: int) -> str:
    names = DAYS_RU if r.lang == "ru" else DAYS_UZ
    word = r.L("ertaga", "завтра") if off else r.L("bugun", "сегодня")
    return f"{word} · {d:%d.%m}, {names[d.weekday()]}"


def _candidates(db) -> list:
    """RD ga qo'yish mumkin bo'lganlar: faol, ega/hamkor emas."""
    return [p for p in P.people(db) if p["kassa_kind"] not in ("self", "partner", "pool")]


@screen("rt", "view")
async def roster_view(ctx, r: Req):
    db = ctx.db
    d, off = _day(ctx, r)
    ui.view(r, f"rt:{off}")
    lines, btn = [], []
    for f in P.folders(db):
        if not f["delay_on"] and not R.workers(db, f["id"], d):
            continue
        w = R.workers(db, f["id"], d)
        mark = " 🔁" if R.override(db, f["id"], d) is not None else ""
        who = ", ".join(h(p["name"]) for p in w) or r.L("❗ <b>hech kim</b>", "❗ <b>никого</b>")
        lines.append(f"{h(f['name'])} — {who}{mark}")
        short = (", ".join(p["name"] for p in w) or "❗")[:22]
        btn.append((f"{f['name']} · {short}", f"rtf:{f['id']}:{off}"))
    rest = R.day_off_people(db, d)
    if rest:
        lines.append("")
        lines.append(f"🛌 {r.L('Dam', 'Выходной')}: " + ", ".join(h(p["name"]) for p in rest))
    if not lines:
        lines = [r.L("Papka yo'q (🚨 Nazorat → 📁 Papkalar).", "Папок нет (🚨 Контроль → 📁 Папки).")]
    note = r.L("🔁 — shu kunga alohida qo'yilgan. RD ni bosing — kim ishlashini tanlang. Belgilash, jarima va "
               "eslatmalar shu ro'yxat bo'yicha; dam olayotgan belgilanmaydi.",
               "🔁 — назначено на этот день. Нажмите RD — выберите, кто работает. Отметки, штрафы и напоминания — по "
               "этому списку; выходных не отмечаем.")
    rows = grid(btn) if r.can("full") else []
    if r.can("full"):
        rows.append([(r.L("🛌 Kim ishlamaydi", "🛌 Кто не работает"), f"rto:{off}")])
    rows.append([(r.L("📅 Bugun", "📅 Сегодня"), "rt:0") if off else (r.L("📆 Ertaga", "📆 Завтра"), "rt:1")])
    rows.append(nav(r))
    return ui.join(title("📅", r.L("KIM QAYERDA", "КТО ГДЕ"), _day_name(r, d, off)), "", card(lines),
                   f"<i>{note}</i>"), kb(*rows)


@screen("rtf", "full")
async def roster_folder(ctx, r: Req):
    """RD ga shu kuni kim: bitta xodim tanlanadi (odatdagisi o'rniga) yoki «odatdagidek»."""
    db = ctx.db
    fid = int(r.args[0])
    f = ui.must(P.folder(db, fid))
    d, off = _day(ctx, r, 1)
    if len(r.args) > 2:
        act = r.args[2]
        if act == "r":
            R.reset(db, fid, d)
        elif act.isdigit():
            R.assign(db, fid, int(act), d)
        ctx.att.recompute_pauses(int(ctx.clock()))
        r.args = [str(off)]
        await ui.toast(ctx.bot, r.chat_id, r.L("✅ Saqlandi", "✅ Сохранено"))
        return await roster_view(ctx, r)
    cur = {p["id"] for p in R.workers(db, fid, d)}
    reg = R.regular(db, fid)
    ov = R.override(db, fid, d)
    reg_txt = ", ".join(h(p["name"]) + (r.L(" (dam)", " (выходной)") if R.resting(db, p, d) else "") for p in reg)
    lines = [r.L(f"Odatda: <b>{reg_txt or '—'}</b>", f"Обычно: <b>{reg_txt or '—'}</b>"),
             r.L("Kim ishlaydi? Bittasini tanlang — shu kunga u belgilanadi va jarima oladi.",
                 "Кто работает? Выберите одного — на этот день отмечается и штрафуется он.")]
    btn = []
    for p in _candidates(db):
        rds = [x["name"] for x in R.person_rds(db, p["id"], d) if x["id"] != fid]
        extra = f" · {', '.join(rds)}" if rds else (r.L(" · dam", " · вых.") if R.resting(db, p, d) and
                                                     P.person_folders(db, p["id"]) else "")
        btn.append(((("● " if p["id"] in cur else "○ ") + p["name"] + extra)[:40], f"rtf:{fid}:{off}:{p['id']}"))
    rows = grid(btn)
    if ov is not None:
        rows.append([(r.L("↩️ Odatdagidek", "↩️ Как обычно") + (f" ({reg[0]['name']})" if reg else ""),
                      f"rtf:{fid}:{off}:r")])
    rows.append(nav(r, f"rt:{off}"))
    return ui.join(title("📅", h(f["name"]), _day_name(r, d, off)), "", card(lines)), kb(*rows)


@screen("rto", "full")
async def roster_off(ctx, r: Req):
    """Shu kuni kim ishlamaydi: bosing — ishlamaydi / ishlaydi (o'z RD larida)."""
    db = ctx.db
    d, off = _day(ctx, r)
    if len(r.args) > 1 and r.args[1].isdigit():
        p = ui.must(P.person(db, int(r.args[1])))
        if R.person_rds(db, p["id"], d):
            R.set_off(db, p["id"], d, True)                    # ishlaydi → bugun ishlamaydi
        else:
            R.set_off(db, p["id"], d, False)                   # dam → ishlaydi (o'z RD larida)
            if not R.person_rds(db, p["id"], d):               # haftalik dam kuni — o'z RD lariga qo'yiladi
                for f in P.person_folders(db, p["id"]):
                    R.assign(db, f["id"], p["id"], d)
        ctx.att.recompute_pauses(int(ctx.clock()))
    btn = []
    for p in _candidates(db):
        if not P.person_folders(db, p["id"]) and not R.person_rds(db, p["id"], d):
            continue
        rds = R.person_rds(db, p["id"], d)
        if rds:
            btn.append((f"▫️ {p['name']} · {', '.join(x['name'] for x in rds)}"[:40], f"rto:{off}:{p['id']}"))
        else:
            btn.append((f"🛌 {p['name']}"[:40], f"rto:{off}:{p['id']}"))
    empty = R.empty_rds(db, d)
    lines = [r.L("Bosing: ▫️ ishlaydi → 🛌 ishlamaydi (va aksincha). Faqat shu kunga. Haftalik dam olish kunlari — "
                 "xodim sozlamalarida (🛌).",
                 "Нажмите: ▫️ работает → 🛌 не работает (и обратно). Только на этот день. Постоянные выходные — в "
                 "настройках сотрудника (🛌).")]
    if empty:
        lines.append(r.L("❗ Hech kim yo'q: ", "❗ Никого: ") + ", ".join(h(f["name"]) for f in empty) +
                     r.L(" — RD ni bosib, kim qarashini tanlang.", " — нажмите RD и выберите, кто смотрит."))
    rows = grid(btn)
    rows += grid([(f"❗ {f['name']}", f"rtf:{f['id']}:{off}") for f in empty])
    rows.append(nav(r, f"rt:{off}"))
    return ui.join(title("🛌", r.L("KIM ISHLAMAYDI", "КТО НЕ РАБОТАЕТ"), _day_name(r, d, off)), "", card(lines)), \
        kb(*rows)


async def morning_check(ctx, now: int) -> None:
    """Ish boshlanishidan 30 daqiqa oldin: bugun hech kim ishlamaydigan RD bo'lsa — egaga, tugma bilan."""
    db = ctx.db
    if not db.flag("bot_enabled") or not db.flag("delay_enabled"):
        return
    from .timeutil import at, parse_hhmm
    d = local_date(now, ctx.tz)
    try:
        start = at(d, parse_hhmm(db.get("work_start")), ctx.tz)
    except ValueError:
        return
    if not start - 1800 <= now <= start + 3 * 3600 or db.get("roster_warn_last") >= d.isoformat():
        return
    db.set("roster_warn_last", d.isoformat())
    empty = R.empty_rds(db, d)
    if not empty:
        return
    from .context import tr
    names = ", ".join(f["name"] for f in empty)

    def build():
        btn = [[(f"❗ {f['name']} — " + tr("kim qaraydi?", "кто смотрит?"), f"rtf:{f['id']}:0")] for f in empty]
        btn.append([(tr("📅 Kim qayerda", "📅 Кто где"), "rt:0")])
        text = tr(f"📅 Bugun <b>{h(names)}</b> da hech kim ishlamaydi (dam olish kuni). Kim qarasin?",
                  f"📅 Сегодня в <b>{h(names)}</b> никто не работает (выходной). Кто смотрит?")
        return text, kb(*btn)
    await ctx.notifier.send_keyed(ctx.notifier.owner_ids(), build, key=f"roster:{d.isoformat()}")
