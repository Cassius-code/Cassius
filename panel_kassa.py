"""💵 Kassa: hisobotlar (formulalar, o'tgan hafta bilan solishtirish), kunlar → akkauntlar → cheklar, «✅ Kunni yopish»,
📋 To'lov ro'yxati (haftalik, Du–Ya), 🗓 Oy yakuni, 📜 Tarix, reyting, cheklar, kim ishladi, zp o'tkazish, ulushlar,
prays, savollar, PDF.

Huquqlar: pul amallari (to'landi, avans, ulushlar, kunni yopish/ochish) — faqat ega. Adminlar cheklarni tuzatadi,
lekin yopilgan kunni faqat ega o'zgartira oladi."""
from __future__ import annotations

import asyncio
import datetime as dt

from . import kassa as K
from . import kassa_flow as F
from . import people as P
from . import ui
from . import kassa_view as V
from .kassa_view import arrow, balance_lines, cmp_note, label as plabel, money, num, overall, rating
from .timeutil import local_date, parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, screen, title, must


def today(ctx) -> dt.date:
    return local_date(ctx.clock(), ctx.tz)


def periods(r: Req, prefix: str, back: str):
    opts = [(r.L("Bugun", "Сегодня"), f"{prefix}:td"), (r.L("Kecha", "Вчера"), f"{prefix}:yd"),
            (r.L("Bu hafta", "Эта неделя"), f"{prefix}:tw"), (r.L("O'tgan hafta", "Прошлая неделя"), f"{prefix}:lw"),
            (r.L("Bu oy", "Этот месяц"), f"{prefix}:tm"), (r.L("O'tgan oy", "Прошлый месяц"), f"{prefix}:lm")]
    return kb(*grid(opts), [(r.L("📆 Sana / oraliq", "📆 Дата / период"), f"{prefix}x")], nav(r, back))


def range_of(ctx, key: str):
    return K.period_range(key, today(ctx))


def dm(d) -> str:
    d = d if isinstance(d, str) else d.isoformat()
    return f"{d[8:10]}.{d[5:7]}"


def locked(ctx, r: Req, *days) -> str | None:
    """Yopilgan kun: faqat ega o'zgartira oladi. -> ogohlantirish matni yoki None."""
    if r.owner:
        return None
    for d in days:
        if d and K.is_closed(ctx.db, d):
            return r.L(f"🔒 {dm(d)} yopilgan — faqat ega o'zgartira oladi",
                       f"🔒 {dm(d)} закрыт — менять может только владелец")
    return None


def visible_acct(r: Req, row: dict) -> bool:
    return r.owner or row["kind"] in ("worker", "pool")


@screen("k", "full")
async def kassa_menu(ctx, r: Req):
    db = ctx.db
    t = today(ctx)
    week = K.calc(db, K.week_start(t), t)
    day = K.calc(db, t, t)
    pend = len(K.pending_reports(db)) + db.scalar("SELECT COUNT(*) FROM adj WHERE pending=1")
    cmp = K.compare(db, K.week_start(t), K.week_start(t) + dt.timedelta(days=6), t)
    lines = [f"📅 {r.L('Bugun', 'Сегодня')} — {num(day['n'])} {r.L('chek', 'чек.')} · <b>{money(day['K'])} $</b>",
             f"🗓 {r.L('Shu hafta', 'Эта неделя')} — {num(week['n'])} {r.L('chek', 'чек.')} · <b>{money(week['K'])} $</b>"
             + (arrow(cmp["K"], cmp["PK"]) if cmp else "")]
    if cmp and cmp["PK"]:
        lines.append(cmp_note(cmp, r.lang))
    zst = K.zp_state(db, K.week_start(t), t, t)
    if r.owner and zst["ready"]:
        lines.append(f"💼 {r.L('Daromadingiz (hafta)', 'Ваш доход (неделя)')} — <b>{money(week['owner']['income'])} $</b>")
    prev_w = K.week_start(t) - dt.timedelta(days=7)
    pst = K.zp_state(db, prev_w, prev_w + dt.timedelta(days=6), t)
    if pst["weeks"]:
        lines.append(f"🧮 {r.L('O‘tgan hafta hisoblanmagan', 'Прошлая неделя не рассчитана')} — {wlabel(prev_w)}")
    open_days = [d for d in recent_days(ctx, 7) if d < t.isoformat() and not K.is_closed(db, d)
                 and K.day_totals(db, d)[0]]
    if open_days:
        lines.append(f"⏳ {r.L('Yopilmagan kunlar', 'Незакрытые дни')} — <b>{', '.join(dm(d) for d in open_days)}</b>")
    if pend:
        lines.append(f"❓ {r.L('Javob kutayotgan savollar', 'Открытые вопросы')} — <b>{pend}</b>")
    items = [(r.L("📊 Hisobot", "📊 Отчёт"), "kr"), (r.L("✅ Kunni yopish", "✅ Закрыть день"), "kc"),
             (r.L("🗓 Oy yakuni", "🗓 Итоги месяца"), "km"), (r.L("🏆 Reyting", "🏆 Рейтинг"), "kg"),
             (r.L("❓ Savollar", "❓ Вопросы") + (f" ({pend})" if pend else ""), "kq"),
             (r.L("💲 Prays", "💲 Прайс"), "kp"), (r.L("📜 Tarix", "📜 История"), "kh"), ("📄 PDF", "kf")]
    if r.owner:
        items = [(r.L("🧮 Haftani hisoblash", "🧮 Рассчитать неделю"), "kz"),
                 (r.L("📋 To'lov ro'yxati", "📋 Ведомость выплат"), "kpay")] + items + \
            [(r.L("🤝 Ulushlar", "🤝 Доли"), "ksh")]
    rows = grid(items)
    rows.append(nav(r))
    return ui.join(title("💵", r.L("KASSA", "КАССА")), "", card(lines)), kb(*rows)


# ───────────────────────── hisobot
@screen("kr", "full")
async def report_menu(ctx, r: Req):
    if r.args:
        return report_show(ctx, r, r.args[0])
    return title("📊", r.L("HISOBOT", "ОТЧЁТ"), r.L("qaysi davr?", "за какой период?")), periods(r, "kr", "k")


def report_show(ctx, r: Req, key: str):
    s, e = range_of(ctx, key)
    b = K.calc(ctx.db, s, e)
    cmp = K.compare(ctx.db, s, e, today(ctx)) if s != e or s < today(ctx) else None
    zst = K.zp_state(ctx.db, s, e, today(ctx))
    text = overall(b, s, e, r.lang, r.owner, cmp, zst)
    pkey = key if key != "td" else s.isoformat()
    people_btn = [(f"👤 {b['rows'][i]['p']['name']}", f"po:{i}:{pkey}")
                  for i in b["order"] if i in b["rows"] and K.has_data(b["rows"][i])
                  and (r.owner or b["rows"][i]["kind"] in ("worker", "pool"))]
    rows = grid(people_btn, 3)
    if r.owner:
        rows += grid([(f"🧮 {wlabel(x)}", f"kz:{x.isoformat()}") for x in zst["weeks"]], 2)
        if s.weekday() == 0 and (e - s).days == 6 and zst["ready"]:
            rows.append([(r.L("🧮 Foizlar", "🧮 Проценты"), f"kz:{s.isoformat()}"),
                         (r.L("📋 To'lov ro'yxati", "📋 Ведомость"), f"kpay:{s.isoformat()}")])
    rows.append([(r.L("📅 Kunlar bo'yicha", "📅 По дням"), f"kd:{pkey}" if s != e else f"kdd:{s.isoformat()}"),
                 ("📄 PDF", f"kf:{key}")])
    rows.append(nav(r, "kr"))
    return clip(text), kb(*rows)


# ───────────────────────── kunlar → akkauntlar → cheklar
def recent_days(ctx, n: int) -> list[str]:
    t = today(ctx)
    return [(t - dt.timedelta(days=i)).isoformat() for i in range(n)]


def days_in(db, s: dt.date, e: dt.date):
    return db.all("SELECT ch.rd d, COUNT(*) n, COALESCE(SUM(ch.usd),0) usd FROM checks ch JOIN reports r "
                  "ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? "
                  "GROUP BY ch.rd ORDER BY ch.rd DESC LIMIT 40", (s.isoformat(), e.isoformat()))


@screen("kd", "full")
async def days_list(ctx, r: Req):
    key = r.args[0] if r.args else "tw"
    s, e = range_of(ctx, key)
    rows_ = days_in(ctx.db, s, e)
    shut = K.closed_days(ctx.db, s, e)
    btn = [(f"{'🔒' if x['d'] in shut else '📅'} {dm(x['d'])} · {x['n']} · {money(x['usd'])} $", f"kdd:{x['d']}")
           for x in rows_]
    text = ui.join(title("📅", r.L("KUNLAR", "ДНИ"), plabel(s, e)), "",
                   card([r.L("Kunni bosing → akkauntlar → cheklar. 🔒 — yopilgan kun.",
                             "Нажмите день → аккаунты → чеки. 🔒 — закрытый день.")]) if btn else
                   r.L("<i>Chek yo'q.</i>", "<i>Чеков нет.</i>"))
    return text, kb(*grid(btn, 2), nav(r, f"kr:{key}"))


def day_text(ctx, r: Req, day: str) -> tuple[str, list]:
    db = ctx.db
    d = dt.date.fromisoformat(day)
    b = K.calc(db, d, d)
    lines, btn = [], []
    tn = traw = 0
    tusd = 0.0
    for i in b["order"]:
        row = b["rows"].get(i)
        if row is None or not row["n"] or not visible_acct(r, row):
            continue
        tag = f" <i>({r.L('umumiy', 'общий')})</i>" if row["kind"] == "pool" else ""
        lines.append(f"{h(row['p']['name'])}{tag} · {num(row['n'])} {r.L('chek', 'чек.')} · {num(row['raw'])} · "
                     f"<b>{money(row['usd'])} $</b>")
        for payee, usd in row["paid_out"].items():
            lines.append(f"   🔁 {h(b['names'].get(payee, '?'))}: {money(usd)} $")
        if row["unassigned"]:
            lines.append(f"   ⚠️ {row['unassigned']} {r.L('chekda kim ishlagani belgilanmagan', 'чек(ов) без исполнителя')}")
        if row["noprice"]:
            lines.append(f"   ⚠️ {row['noprice']} {r.L('chek narxsiz', 'чек(ов) без цены')}")
        tn, traw, tusd = tn + row["n"], traw + row["raw"], tusd + row["usd"]
        btn.append((f"🧾 {row['p']['name']}", f"kxd:{i}:{day}"))
    parts = []
    if lines:
        lines.append(f"<b>{r.L('Jami', 'Итого')}</b> · {num(tn)} {r.L('chek', 'чек.')} · {num(traw)} · "
                     f"<b>{money(tusd)} $</b>")
        parts.append(card([f"<b>💵 {r.L('Kassa', 'Касса')}</b>"] + lines))
    else:
        parts.append(r.L("<i>Bu kunda chek yo'q.</i>", "<i>За этот день чеков нет.</i>"))
    if r.owner and lines and K.zp_state(db, d, d, today(ctx))["ready"]:
        parts.append(card(balance_lines(b, r.lang)))
    info = []
    c = K.closed(db, day)
    if c is not None:
        when = dt.datetime.fromtimestamp(c["ts"], ctx.tz).strftime("%d.%m %H:%M")
        info.append(f"🔒 <b>{r.L('Kun yopilgan', 'День закрыт')}</b> · {when} · {money(c['usd'])} $")
        n, _raw, usd = K.day_totals(db, day)
        if abs(usd - c["usd"]) >= 0.01 or n != c["n"]:
            info.append(f"✏️ {r.L('Yopilgandan keyin o‘zgardi', 'Изменён после закрытия')}: {money(c['usd'])} → "
                        f"<b>{money(usd)} $</b>")
    else:
        info.append(f"⏳ {r.L('Kun ochiq', 'День открыт')}")
    pend = len(K.pending_reports(db)) + db.scalar("SELECT COUNT(*) FROM adj WHERE pending=1")
    if pend:
        info.append(f"❓ {r.L('Javob kutayotgan savollar', 'Открытые вопросы')}: <b>{pend}</b> — "
                    f"{r.L('avval javob bering', 'сначала ответьте')}")
    nh = db.scalar("SELECT COUNT(*) FROM audit WHERE day=?", (day,))
    if nh:
        info.append(f"📜 {r.L('O‘zgartirishlar', 'Изменений')}: {nh}")
    parts.append(card(info))
    return ui.join(*parts), btn


@screen("kdd", "full")
async def day_show(ctx, r: Req):
    day = r.args[0]
    text, btn = day_text(ctx, r, day)
    rows = grid(btn, 2)
    extra = [(r.L("📜 Tarix", "📜 История"), f"kh:0:{day}")]
    if r.owner:
        if K.is_closed(ctx.db, day):
            extra.append((r.L("🔓 Kunni ochish", "🔓 Открыть день"), f"kco:{day}"))
        else:
            extra.append((r.L("🔒 Kunni yopish", "🔒 Закрыть день"), f"kcy:{day}"))
    rows += grid(extra, 2)
    rows.append(nav(r, "kc"))
    d = dt.date.fromisoformat(day)
    wd = [r.L(x, y) for x, y in (("Du", "Пн"), ("Se", "Вт"), ("Ch", "Ср"), ("Pa", "Чт"), ("Ju", "Пт"), ("Sh", "Сб"),
                                  ("Ya", "Вс"))][d.weekday()]
    return ui.join(title("📅", f"{dm(day)} · {wd}"), "", text), kb(*rows)


@screen("kc", "full")
async def close_menu(ctx, r: Req):
    db = ctx.db
    btn = []
    for d in recent_days(ctx, 10):
        n, _raw, usd = K.day_totals(db, d)
        mark = "🔒" if K.is_closed(db, d) else ("⏳" if n else "·")
        btn.append((f"{mark} {dm(d)} · {n} · {money(usd)} $", f"kdd:{d}"))
    hint = (r.L("Hamma hisobotlar tushgach kunni oching va «🔒 Kunni yopish» ni bosing. Yopilgan kunni faqat siz "
                "o'zgartira olasiz; yopilgan kunga yangi hisobot kelsa, sizga xabar keladi.",
                "Когда все отчёты пришли — откройте день и нажмите «🔒 Закрыть день». Закрытый день меняете только "
                "вы; если на закрытый день придёт новый отчёт — вам придёт сообщение.") if r.owner else
            r.L("Kunni ega yopadi. Yopilgan kunni faqat ega o'zgartira oladi.",
                "День закрывает владелец. Закрытый день менять может только владелец."))
    return ui.join(title("✅", r.L("KUNNI YOPISH", "ЗАКРЫТИЕ ДНЯ"), r.L("🔒 yopilgan · ⏳ ochiq",
                                                                        "🔒 закрыт · ⏳ открыт")), "",
                   card([hint])), kb(*grid(btn, 2), nav(r, "k"))


@screen("kcy", "owner")
async def close_do(ctx, r: Req):
    day = r.args[0]
    K.close_day(ctx.db, day)
    await ui.toast(ctx.bot, r.chat_id, r.L(f"🔒 {dm(day)} yopildi", f"🔒 {dm(day)} закрыт"))
    return await day_show(ctx, r)


@screen("kco", "owner")
async def open_do(ctx, r: Req):
    day = r.args[0]
    K.open_day(ctx.db, day)
    await ui.toast(ctx.bot, r.chat_id, r.L(f"🔓 {dm(day)} ochildi", f"🔓 {dm(day)} открыт"))
    return await day_show(ctx, r)


@screen("kcl", "owner")
async def closed_report(ctx, r: Req):
    """Yopilgan kunga yangi hisobot keldi: qolsinmi?"""
    db = ctx.db
    rid, op = int(r.args[0]), r.args[1]
    rep = K.report(db, rid)
    if rep is None:
        return await _edit_q(ctx, r, r.L("ℹ️ Hisobot o'chirilgan.", "ℹ️ Отчёт удалён."))
    if op == "x":
        K.set_report_status(db, rid, "excluded")
        return await _edit_q(ctx, r, r.L("🚫 Hisobga olinmadi.", "🚫 Не учитывается."),
                             kb([(r.L("↩️ Qaytarish", "↩️ Вернуть"), f"kcl:{rid}:r")]))
    if op == "r":
        K.set_report_status(db, rid, "done")
    return await _edit_q(ctx, r, r.L("✅ Hisobda qoldi.", "✅ Оставлено в расчёте."),
                         kb([(r.L("🚫 Hisobga olinmasin", "🚫 Не учитывать"), f"kcl:{rid}:x")]))


def clip(text: str, limit: int = 3900) -> str:
    """Telegram 4096 belgi: juda uzun bo'lsa oxiri qisqartiriladi (to'liq — PDF da)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    opens = cut.count("<blockquote") - cut.count("</blockquote>")
    cut = cut[:cut.rfind("\n")]
    for tag in ("b", "i"):
        if cut.count(f"<{tag}>") > cut.count(f"</{tag}>"):
            cut += f"</{tag}>"
    return cut + "\n…" + ("</blockquote>" * max(0, opens))


@screen("krx", "full")
async def report_date_ask(ctx, r: Req):
    ui.ask(r, "report_date", "kr")
    return title("📆", r.L("DAVR", "ПЕРИОД")) + "\n\n" + card(
        [r.L("Sana (<code>05.10</code>) yoki oraliq (<code>05.10-11.10</code>).",
             "Дата (<code>05.10</code>) или период (<code>05.10-11.10</code>).")]), ui.cancel_kb(r, "kr")


@on_input("report_date")
async def report_date(ctx, r: Req):
    ds = K.parse_dates(r.text, today(ctx))
    if not ds:
        return r.L("⚠️ Masalan: 05.10-11.10", "⚠️ Например: 05.10-11.10")
    key = ds[0].isoformat() if len(ds) == 1 else f"{min(ds[:2]).isoformat()}_{max(ds[:2]).isoformat()}"
    return report_show(ctx, r, key)


@screen("kg", "full")
async def rating_menu(ctx, r: Req):
    if r.args:
        s, e = range_of(ctx, r.args[0])
        return rating(K.calc(ctx.db, s, e), s, e, r.lang), kb(nav(r, "kg"))
    return title("🏆", r.L("REYTING", "РЕЙТИНГ"), r.L("qaysi davr?", "за какой период?")), periods(r, "kg", "k")


@screen("kgx", "full")
async def rating_date_ask(ctx, r: Req):
    return await report_date_ask(ctx, r)


# ───────────────────────── PDF
@screen("kf", "full")
async def pdf(ctx, r: Req):
    if not r.args:
        return title("📄", "PDF", r.L("qaysi davr?", "за какой период?")), periods(r, "kf", "k")
    key = r.args[0]
    s, e = range_of(ctx, key)
    from . import pdfgen
    b = K.calc(ctx.db, s, e)
    zp = K.zp_state(ctx.db, s, e, today(ctx))["ready"]
    try:
        data = await asyncio.to_thread(pdfgen.overall_pdf, b, s, e, r.lang, r.owner, zp)
    except Exception as exc:
        return r.L(f"⚠️ PDF yaratilmadi: {h(exc)}", f"⚠️ PDF не создан: {h(exc)}")
    await ctx.notifier.send_document(r.chat_id, data, f"kassa_{s.isoformat()}_{e.isoformat()}.pdf",
                                     f"📄 {plabel(s, e)}")
    return None


@screen("kfx", "full")
async def pdf_date_ask(ctx, r: Req):
    return await report_date_ask(ctx, r)


# ───────────────────────── 📋 To'lov ro'yxati (haftalik: dushanba – yakshanba, to'liq to'lanadi)
def pay_rows(db, s: dt.date, e: dt.date):
    b = K.calc(db, s, e)
    out = []
    for i in b["order"]:
        row = b["rows"].get(i)
        if row is None or row["kind"] not in ("worker", "partner") or not K.has_data(row):
            continue
        out.append((row, K.week_payout(db, i, e)))
    return out


def week_of(ctx, r: Req) -> tuple[dt.date, dt.date]:
    t = today(ctx)
    s = dt.date.fromisoformat(r.args[0]) if r.args else K.week_start(t) - dt.timedelta(days=7)
    s = K.week_start(s)
    return s, s + dt.timedelta(days=6)


@screen("kpay", "owner")
async def pay_list(ctx, r: Req):
    db = ctx.db
    s, e = week_of(ctx, r)
    t = today(ctx)
    zst = K.zp_state(db, s, e, t)
    if zst["mode"] == "button" and not zst["ready"]:
        prev_s, next_s = s - dt.timedelta(days=7), s + dt.timedelta(days=7)
        navw = [(f"‹ {dm(prev_s)}", f"kpay:{prev_s.isoformat()}")]
        if next_s <= K.week_start(t):
            navw.append((f"{dm(next_s)} ›", f"kpay:{next_s.isoformat()}"))
        return ui.join(title("📋", r.L("TO‘LOV RO‘YXATI", "ВЕДОМОСТЬ ВЫПЛАТ"), plabel(s, e)), "",
                       card([r.L("🧮 Avval haftani hisoblang: foizlarni tasdiqlaysiz, keyin ro'yxat chiqadi.",
                                 "🧮 Сначала рассчитайте неделю: подтвердите проценты, потом будет ведомость.")])), \
            kb([(r.L("🧮 Haftani hisoblash", "🧮 Рассчитать неделю"), f"kz:{s.isoformat()}")], navw, nav(r, "k"))
    items = pay_rows(db, s, e)
    lines, btn = [], []
    total = paid = 0.0
    for row, po in items:
        nm = row["p"]["name"] + (r.L(" (hamkor)", " (партнёр)") if row["kind"] == "partner" else "")
        amt = (f"{money(row['total'])} $" if row["total"] is not None and zst["ready"] else
               r.L("o'zingiz hisoblaysiz", "считаете сами"))
        if po:
            when = dt.datetime.fromtimestamp(po["ts"], ctx.tz).strftime("%d.%m")
            lines.append(f"✅ {h(nm)} — {amt} · <i>{r.L('to‘landi', 'выплачено')} {when}</i>")
            btn.append((f"↩️ {row['p']['name']}", f"kpu:{s.isoformat()}:{row['p']['id']}"))
            paid += po["total"] or 0
        else:
            lines.append(f"⏳ {h(nm)} — <b>{amt}</b>")
            btn.insert(0, (f"✅ {row['p']['name']} · {amt}", f"kpy:{s.isoformat()}:{row['p']['id']}"))
        total += row["total"] or 0
    if lines:
        lines += ["", f"{r.L('Jami', 'Итого')}: <b>{money(total)} $</b> · {r.L('to‘landi', 'выплачено')} "
                      f"{money(paid)} $ · {r.L('qoldi', 'осталось')} <b>{money(max(total - paid, 0))} $</b>"]
    notes = [r.L("Bosing — «to'landi» deb belgilanadi. Hafta to'liq to'lanadi, keyingi hafta noldan.",
                 "Нажмите — отметится «выплачено». Неделя выплачивается целиком, следующая — с нуля.")]
    if e >= t:
        notes.insert(0, r.L("⚠️ Hafta hali tugamagan — raqamlar o'zgarishi mumkin.",
                            "⚠️ Неделя ещё не закончилась — суммы могут измениться."))
    rows = [[x] for x in btn]
    if any(po is None for _row, po in items) and len(items) > 1:
        rows.append([(r.L("✅ Hammasi to'landi", "✅ Выплачено всем"), f"kpy:{s.isoformat()}:0")])
    prev_s, next_s = s - dt.timedelta(days=7), s + dt.timedelta(days=7)
    navw = [(f"‹ {dm(prev_s)}", f"kpay:{prev_s.isoformat()}")]
    if next_s <= K.week_start(t):
        navw.append((f"{dm(next_s)} ›", f"kpay:{next_s.isoformat()}"))
    rows.append(navw)
    rows.append(nav(r, "k"))
    text = ui.join(title("📋", r.L("TO‘LOV RO‘YXATI", "ВЕДОМОСТЬ ВЫПЛАТ"), f"{plabel(s, e)} · "
                         + r.L("Du–Ya", "Пн–Вс")), "",
                   card(lines) if lines else r.L("<i>Bu haftada hisob yo'q.</i>", "<i>За эту неделю начислений нет.</i>"),
                   card(notes))
    return text, kb(*rows)


@screen("kpy", "owner")
async def pay_mark(ctx, r: Req):
    db = ctx.db
    s = dt.date.fromisoformat(r.args[0])
    e = s + dt.timedelta(days=6)
    pid = int(r.args[1])
    n = 0
    for row, po in pay_rows(db, s, e):
        if po is None and pid in (0, row["p"]["id"]):
            K.mark_paid(db, row["p"]["id"], e, row["total"] if K.zp_mode(db) != "off" else None, note="week")
            n += 1
    await ui.toast(ctx.bot, r.chat_id, r.L(f"✅ To'landi: {n}", f"✅ Выплачено: {n}"))
    r.args = [s.isoformat()]
    return await pay_list(ctx, r)


@screen("kpu", "owner")
async def pay_undo(ctx, r: Req):
    db = ctx.db
    s = dt.date.fromisoformat(r.args[0])
    e = s + dt.timedelta(days=6)
    pid = int(r.args[1])
    po = db.one("SELECT id FROM payouts WHERE person_id=? AND upto_day=? ORDER BY id DESC LIMIT 1", (pid, e.isoformat()))
    if po is None:
        return r.L("ℹ️ Bu to'lov keyingi hafta bilan birga belgilangan — o'sha haftadan bekor qiling.",
                   "ℹ️ Эта выплата отмечена вместе со следующей неделей — отмените там.")
    K.undo_paid(db, po["id"])
    await ui.toast(ctx.bot, r.chat_id, r.L("↩️ Bekor qilindi", "↩️ Отменено"))
    r.args = [s.isoformat()]
    return await pay_list(ctx, r)


# ───────────────────────── 🗓 Oy yakuni
MONTH_UZ = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"]
MONTH_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь",
            "Декабрь"]


def month_name(r: Req, m: int) -> str:
    return (MONTH_RU if r.lang == "ru" else MONTH_UZ)[m - 1]


@screen("km", "full")
async def month_report(ctx, r: Req):
    db = ctx.db
    t = today(ctx)
    try:
        y, m = (int(x) for x in r.args[0].split("-")) if r.args else (t.year, t.month)
        dt.date(y, m, 1)
    except (ValueError, TypeError):
        y, m = t.year, t.month
    md = K.month_data(db, y, m, t)
    b, cmp = md["b"], md["cmp"]
    ch = r.L("chek", "чек.")
    head = [f"<b>💵 {r.L('Kassa', 'Касса')}</b>",
            f"{num(b['n'])} {ch} · {num(b['raw'])} · <b>{money(b['K'])} $</b>" + (arrow(cmp["K"], cmp["PK"]) if cmp else "")]
    note = cmp_note(cmp, r.lang)
    if note:
        head.append(note)
    if md["days"]:
        head.append(f"📆 {r.L('Ish kunlari', 'Рабочих дней')}: {md['days']} · {r.L('kuniga o‘rtacha', 'в среднем в день')} "
                    f"{money(b['K'] / md['days'])} $")
    if md["best"]:
        head.append(f"🏅 {r.L('Eng yaxshi kun', 'Лучший день')}: {dm(md['best'][0])} — {money(md['best'][1])} $")
    parts = [card(head)]
    wl = [f"<b>📅 {r.L('Haftalar', 'Недели')}</b>"]
    for wk in md["weeks"]:
        wl.append(f"{plabel(wk['s'], wk['e'])} · {num(wk['n'])} {ch} · <b>{money(wk['usd'])} $</b>")
    if len(wl) > 1:
        parts.append(card(wl))
    top = sorted([x for x in b["rows"].values() if x["n"] and x["kind"] in ("worker", "self", "pool")
                  and visible_acct(r, x)], key=lambda x: -x["usd"])[:5]
    if top:
        medal = ["🥇", "🥈", "🥉", "4.", "5."]
        parts.append(card([f"<b>🏆 {r.L('Top', 'Топ')}</b>"] + [f"{medal[i]} {h(x['p']['name'])} — <b>{money(x['usd'])} $</b>"
                                                              f" · {num(x['n'])} {ch}" for i, x in enumerate(top)]))
    zp = [x for x in b["rows"].values() if x["kind"] == "worker" and x["total"] is not None and K.has_data(x)]
    mz = K.zp_state(db, md["first"], md["last"], t)
    if zp and mz["ready"]:
        zl = [f"<b>💰 {r.L('Xodimlar zp', 'Зарплаты')}</b>"]
        for x in sorted(zp, key=lambda x: -(x["total"] or 0)):
            extra = []
            if x["fine"]:
                extra.append(f"{r.L('jarima', 'штраф')} {money(x['fine'])}")
            if x["bonus"]:
                extra.append(f"{r.L('bonus', 'бонус')} {money(x['bonus'])}")
            zl.append(f"{h(x['p']['name'])} — <b>{money(x['total'])} $</b>" + (f" <i>({', '.join(extra)})</i>" if extra else ""))
        parts.append(card(zl))
    if not mz["ready"]:
        parts.append(card([V.zp_note(mz, r.lang, r.owner)]))
    if r.owner and b["n"] and mz["ready"]:
        o = b["owner"]
        parts.append(card([f"<b>💼 {r.L('Siz', 'Вы')}</b> · <i>{r.L('faqat sizga ko‘rinadi', 'видно только вам')}</i>",
                           f"{r.L('Artur', 'Артур')}: {money(o['partner_total'])} $",
                           f"{r.L('Daromadingiz', 'Ваш доход')}: <b>{money(o['income'])} $</b>"] + balance_lines(b, r.lang)))
    first, last = md["first"], md["last"]
    pm = (first - dt.timedelta(days=1))
    nm = last + dt.timedelta(days=1)
    navm = [(f"‹ {month_name(r, pm.month)}", f"km:{pm.year}-{pm.month:02d}")]
    if nm <= t:
        navm.append((f"{month_name(r, nm.month)} ›", f"km:{nm.year}-{nm.month:02d}"))
    key = f"{first.isoformat()}_{last.isoformat()}"
    wk_btn = grid([(f"🧮 {wlabel(x)}", f"kz:{x.isoformat()}") for x in mz["weeks"]], 2) if r.owner else []
    rows = wk_btn + [navm, [(r.L("📊 To'liq hisobot", "📊 Полный отчёт"), f"kr:{key}"), ("📄 PDF", f"kf:{key}")], nav(r, "k")]
    text = ui.join(title("🗓", f"{month_name(r, m).upper()} {y}", r.L("oy yakuni", "итоги месяца")
                         + (r.L(" · davom etmoqda", " · ещё идёт") if last > t else "")), "",
                   *parts if b["n"] else [r.L("<i>Bu oyda chek yo'q.</i>", "<i>За этот месяц чеков нет.</i>")])
    return clip(text), kb(*rows)


# ───────────────────────── 📜 Tarix
def actor_name(ctx, uid) -> str:
    if uid is None:
        return "🤖"
    if uid in ctx.cfg.owner_ids:
        return "👑"
    a = ctx.db.one("SELECT name, level FROM admins WHERE user_id=?", (uid,))
    if a is not None:
        return ("👑 " if a["level"] == "owner" else "👮 ") + (a["name"] or str(uid))
    p = P.by_tg(ctx.db, uid)
    return f"👤 {p['name']}" if p else str(uid)


def hist_line(ctx, r: Req, a, names: dict) -> str:
    k, old, new = a["kind"], a["old"], a["new"]
    who = h(names.get(a["person_id"], "")) if a["person_id"] else ""
    day = dm(a["day"]) if a["day"] else ""
    pd = f"{who} {day}".strip()
    word = {"fine": r.L("jarima", "штраф"), "bonus": r.L("bonus", "бонус"), "adv": r.L("avans", "аванс")}

    def adj_txt(v: str) -> str:
        kind, _, usd = v.partition(" ")
        return f"{word.get(kind, kind)} {usd} $"
    if k == "chk_amt":
        t = f"✏️ {pd}: {num(int(old))} → <b>{num(int(new))}</b>"
    elif k == "chk_add":
        t = f"➕ {pd}: {r.L('chek', 'чек')} <b>{num(int(new))}</b>"
    elif k == "chk_day":
        t = f"📅 {who}: {r.L('chek', 'чек')} {num(int(new))} · {dm(old) if old else '?'} → <b>{day}</b>"
    elif k == "chk_skip":
        t = (f"🚫 {pd}: {num(int(old))} {r.L('sanalmaydi', 'не считается')}" if new == "off" else
             f"✅ {pd}: {num(int(old))} {r.L('yana sanaladi', 'снова считается')}")
    elif k == "day_clear":
        t = f"🗑 {pd}: {r.L('kun o‘chirildi', 'день удалён')} ({h(old)})"
    elif k == "rep_edit":
        t = f"✏️ {pd}: {r.L('guruhda tahrirlandi', 'изменено в группе')} {h(old)} → <b>{h(new)}</b>"
    elif k == "rep_replaced":
        t = f"♻️ {pd}: {r.L('eski hisobot almashtirildi', 'старый отчёт заменён')} ({h(old)})"
    elif k == "rep_excluded":
        t = f"🚫 {pd}: {r.L('hisobot hisobdan chiqarildi', 'отчёт исключён')} ({h(old)})"
    elif k.startswith("rep_"):
        t = f"↩️ {pd}: {r.L('hisobot qaytarildi', 'отчёт возвращён')} ({h(old)})"
    elif k == "pay_day":
        to = names.get(a["ref_id"]) if a["ref_id"] else r.L("akkaunt egasi", "владелец аккаунта")
        t = f"🔁 {pd}: {r.L('ishlagan', 'работал')} — {h(to)}"
    elif k == "adj_add":
        src = {"delay": r.L(" · avto (zaderjka)", " · авто (задержка)"), "late": r.L(" · avto (kech qoldi)", " · авто (опоздание)"),
               "group": r.L(" · guruhdan", " · из группы")}.get(old, "")
        icon = "🎁" if new.startswith("bonus") else ("💸" if new.startswith("adv") else "⚠️")
        t = f"{icon} {pd}: {adj_txt(new)}{src}"
    elif k in ("adj_off", "adj_on"):
        t = (f"✖️ {pd}: {adj_txt(new)} {r.L('bekor qilindi', 'отменён')}" if k == "adj_off" else
             f"↩️ {pd}: {adj_txt(new)} {r.L('qaytarildi', 'возвращён')}")
    elif k == "price":
        t = f"💲 {r.L('Prays', 'Прайс')}: " + (f"{h(old)} → <b>{h(new)}</b>" if old and new else
                                                f"➕ {h(new)}" if new else f"🗑 {h(old)}")
    elif k.startswith("transfer"):
        to = h(names.get(a["ref_id"], "?"))
        mark = {"transfer_off": "✖️ ", "transfer_on": "↩️ "}.get(k, "")
        t = f"🔀 {mark}{pd} → {to}: {new}%"
    elif k == "share":
        fr = h(names.get(a["ref_id"], "?"))
        t = f"🤝 {who} ← {fr}: " + (f"{old}% → <b>{new}%</b>" if old and new else f"➕ {new}%" if new else f"🗑 {old}%")
    elif k == "pct":
        since = r.L("hamma vaqt", "всё время") if a["day"] == "2000-01-01" else \
            r.L(f"{day} dan", f"с {day}")
        t = f"📈 {who}: {r.L('foiz', 'процент')} {old}% → <b>{new}%</b> ({since})"
    elif k == "opct":
        t = (f"📐 {who}: {r.L('sizning foizingiz', 'ваш процент')} " + (f"{old}% → " if old else "") +
             f"<b>{new}%</b> ({r.L(f'{day} dan', f'с {day}')})")
    elif k == "week_ok":
        d0 = dt.date.fromisoformat(a["day"])
        t = f"🧮 {r.L('Hafta hisoblandi', 'Неделя рассчитана')}: {wlabel(d0)}"
    elif k == "week_open":
        d0 = dt.date.fromisoformat(a["day"])
        t = f"↩️ {r.L('Hafta qayta ochildi', 'Неделя открыта заново')}: {wlabel(d0)}"
    elif k == "paid":
        t = f"✅ {who}: {r.L('to‘landi', 'выплачено')} {day} {r.L('gacha', 'по')}" + (f" · {new} $" if new else "")
    elif k == "paid_undo":
        t = f"↩️ {who}: {r.L('to‘lov bekor qilindi', 'выплата отменена')} ({day})"
    elif k == "day_close":
        t = f"🔒 {day} {r.L('yopildi', 'закрыт')}"
    elif k == "day_open":
        t = f"🔓 {day} {r.L('ochildi', 'открыт')}"
    else:
        t = f"{h(k)} {pd} {h(old)} {h(new)}"
    when = dt.datetime.fromtimestamp(a["ts"], ctx.tz).strftime("%d.%m %H:%M")
    return f"<i>{when}</i> · {h(actor_name(ctx, a['actor']))}\n{t}"


def hist_visible(r: Req, a, kinds: dict) -> bool:
    if r.owner:
        return True
    if a["kind"] in ("share", "paid", "paid_undo"):
        return False
    for pid in (a["person_id"], a["ref_id"] if a["kind"].startswith(("transfer", "pay_day")) else None):
        if pid and kinds.get(pid) in ("self", "partner"):
            return False
    return True


@screen("kh", "full")
async def history(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0]) if r.args and r.args[0] != "0" else None
    day = r.args[1] if len(r.args) > 1 and r.args[1] != "-" else None
    ppl = db.all("SELECT id, name, kassa_kind FROM people")
    names = {p["id"]: p["name"] for p in ppl}
    kinds = {p["id"]: p["kassa_kind"] for p in ppl}
    rows_ = [a for a in K.history(db, day, pid, 40) if hist_visible(r, a, kinds)][:15]
    sub = " · ".join(x for x in (h(names.get(pid, "")) if pid else "", dm(day) if day else "") if x) or \
        r.L("oxirgi o'zgartirishlar", "последние изменения")
    body = "\n\n".join(hist_line(ctx, r, a, names) for a in rows_)
    text = ui.join(title("📜", r.L("TARIX", "ИСТОРИЯ"), sub), "",
                   f"<blockquote expandable>{body}</blockquote>" if body else
                   r.L("<i>O'zgartirish yo'q.</i>", "<i>Изменений нет.</i>"))
    back = f"kxd:{pid}:{day}" if pid and day else (f"kdd:{day}" if day else (f"po:{pid}" if pid else "k"))
    return clip(text), kb(nav(r, back))


# ───────────────────────── prays
@screen("kp", "full")
async def prices(ctx, r: Req):
    rows = []
    for p in K.prices(ctx.db):
        rng = num(p["lo"]) if p["lo"] == p["hi"] else f"{num(p['lo'])}–{num(p['hi'])}"
        rows.append((f"{rng} = {money(p['usd'])} $", f"kpe:{p['id']}"))
    kbr = grid(rows) + [[(r.L("➕ Narx qo'shish", "➕ Добавить цену"), "kpa")], nav(r, "k")]
    note = r.L("Chek narxi yozilgan paytda qotadi: prays o'zgarsa, o'tgan cheklar o'zgarmaydi.",
               "Цена чека фиксируется при записи: изменение прайса не меняет прошлые чеки.")
    return ui.join(title("💲", r.L("PRAYS", "ПРАЙС")), "", card([note])), kb(*kbr)


@screen("kpa", "full")
async def price_add_ask(ctx, r: Req):
    ui.ask(r, "price", "kp", pid=0)
    return title("💲", r.L("NARX", "ЦЕНА")) + "\n\n" + card(
        [r.L("«summa narx» (<code>5200 20</code>) yoki «dan gacha narx» (<code>5000 5400 20</code>).",
             "«сумма цена» (<code>5200 20</code>) или «от до цена» (<code>5000 5400 20</code>).")]), \
        ui.cancel_kb(r, "kp")


@screen("kpe", "full")
async def price_edit(ctx, r: Req):
    pid = int(r.args[0])
    p = ctx.db.one("SELECT * FROM prices WHERE id=?", (pid,))
    if p is None:
        return await prices(ctx, r)
    ui.ask(r, "price", "kp", pid=pid)
    rng = num(p["lo"]) if p["lo"] == p["hi"] else f"{num(p['lo'])}–{num(p['hi'])}"
    return ui.join(title("💲", f"{rng} = {money(p['usd'])} $"), "", card(
        [r.L("Yangi qiymatni yuboring: <code>5200 20</code> yoki <code>5000 5400 20</code>.",
             "Пришлите новое значение: <code>5200 20</code> или <code>5000 5400 20</code>.")])), \
        kb([(r.L("🗑 O'chirish", "🗑 Удалить"), f"kpd:{pid}")], [(r.L("✖️ Bekor qilish", "✖️ Отмена"), "kp")])


@screen("kpd", "full")
async def price_delete(ctx, r: Req):
    K.del_price(ctx.db, int(r.args[0]))
    return await prices(ctx, r)


@on_input("price")
async def price_set(ctx, r: Req, pid: int = 0, rid: int = 0):
    nums = [parse_number(x) for x in r.text.split()]
    if rid and len(nums) == 1 and nums[0]:                 # savolga javob: faqat narx
        amount = int(K.report(ctx.db, rid) and ctx.db.scalar(
            "SELECT amount FROM checks WHERE report_id=? AND usd IS NULL LIMIT 1", (rid,)) or 0)
        nums = [amount, nums[0]] if amount else []
    if None in nums or len(nums) not in (2, 3):
        return r.L("⚠️ Masalan: 5200 20", "⚠️ Например: 5200 20")
    lo, hi, usd = (int(nums[0]), int(nums[0]), nums[1]) if len(nums) == 2 else (int(nums[0]), int(nums[1]), nums[2])
    if pid:
        K.update_price(ctx.db, pid, lo, hi, usd)
    else:
        K.add_price(ctx.db, lo, hi, usd)
    for rr in K.pending_reports(ctx.db):
        if K.report_needs(ctx.db, rr) is None:
            await F.finalize(ctx, rr)
    return await prices(ctx, r)


# ───────────────────────── savollar (alohida xabarlar; tugma o'sha xabarni o'zgartiradi)
@screen("kq", "full")
async def questions(ctx, r: Req):
    n = await F.repeat_questions(ctx)
    if not n:
        return r.L("😊 Ochiq savol yo'q", "😊 Открытых вопросов нет")
    await ui.toast(ctx.bot, r.chat_id, r.L(f"❓ {n} ta savol pastda", f"❓ {n} вопрос(а) ниже"))
    return None


async def _edit_q(ctx, r: Req, text: str, markup=None):
    try:
        await ctx.bot.edit_message_text(text, chat_id=r.chat_id, message_id=r.message.message_id, parse_mode="HTML",
                                        reply_markup=markup)
    except Exception:
        pass


@screen("qok", "full")
async def q_ok(ctx, r: Req):
    await _edit_q(ctx, r, r.L("👌 Ikkalasi qoldi.", "👌 Оставил оба."))


@screen("qr", "full")
async def q_report(ctx, r: Req):
    db = ctx.db
    rid, op, arg = int(r.args[0]), r.args[1], r.args[2]
    rep = K.report(db, rid)
    if op == "r":                                           # eski hisobotni qaytarish
        K.set_report_status(db, rid, "done")
        return await _edit_q(ctx, r, r.L("↩️ Eski hisobot qaytarildi (ikkalasi sanaladi).",
                                         "↩️ Старый отчёт возвращён (считаются оба)."))
    if op == "u":
        K.set_report_status(db, rid, "replaced")
        return await _edit_q(ctx, r, r.L("✅ Takror olib tashlandi.", "✅ Повтор убран."))
    if rep is None or rep["status"] == "done" and op not in ("o",):
        return await _edit_q(ctx, r, r.L("✅ Allaqachon hal qilingan.", "✅ Уже решено."))
    if op == "x":
        K.delete_report(db, rid)
        return await _edit_q(ctx, r, r.L("🚫 Bu xabar hisobga olinmaydi.", "🚫 Сообщение не учитывается."))
    if op == "p":
        if rep["person_id"] is not None:
            return await _edit_q(ctx, r, r.L("✅ Allaqachon hal qilingan.", "✅ Уже решено."))
        db.run("UPDATE reports SET person_id=? WHERE id=?", (int(arg), rid))
        p = must(P.person(db, int(arg)))
        sid = rep["sender_id"]
        if sid and P.admin_level(db, ctx.cfg.owner_ids, sid) == "" and not P.by_tg(db, sid) and p["kassa_kind"] == "worker" \
                and not p["tg_id"]:
            P.update_person(db, p["id"], tg_id=sid)          # keyingi safar o'zi taniydi
        await _edit_q(ctx, r, f"✅ {h(p['name'])}")
    elif op == "d":
        db.run("UPDATE checks SET rd=? WHERE report_id=? AND rd IS NULL", (arg, rid))
        await _edit_q(ctx, r, f"✅ {arg[8:10]}.{arg[5:7]}")
    elif op == "$":
        ui.ask(r, "price", "k", pid=0, rid=rid)
        await _edit_q(ctx, r, r.L(f"💲 {num(int(arg))} — necha $? Javob sifatida sonni yozing (masalan 12).",
                                  f"💲 {num(int(arg))} — сколько $? Напишите число (например 12)."))
        return None
    elif op == "o":
        if K.report_needs(db, rid) != ("op", None):
            return await _edit_q(ctx, r, r.L("✅ Allaqachon hal qilingan.", "✅ Уже решено."))
        K.set_pay_report(db, rid, int(arg))
        await _edit_q(ctx, r, f"✅ {h(P.person(db, int(arg))['name'])}")
    await F.advance(ctx, rid)
    return None


@screen("qa", "full")
async def q_adj(ctx, r: Req):
    db = ctx.db
    aid, op, arg = int(r.args[0]), r.args[1], r.args[2]
    a = K.adj(db, aid)
    if a is None or not a["pending"]:
        return await _edit_q(ctx, r, r.L("✅ Allaqachon hal qilingan.", "✅ Уже решено."))
    if op == "x":
        db.run("DELETE FROM adj WHERE id=?", (aid,))
        return await _edit_q(ctx, r, r.L("✖️ Bekor qilindi.", "✖️ Отменено."))
    if op == "p":
        db.run("UPDATE adj SET person_id=? WHERE id=?", (int(arg), aid))
    elif op == "k":
        db.run("UPDATE adj SET kind=? WHERE id=?", (arg, aid))
    a = must(K.adj(db, aid))
    if a["person_id"] and a["kind"]:
        db.run("UPDATE adj SET pending=0 WHERE id=?", (aid,))
        word = {"fine": r.L("jarima", "штраф"), "bonus": r.L("bonus", "бонус"), "adv": r.L("avans", "аванс")}[a["kind"]]
        return await _edit_q(ctx, r, f"✅ {h(P.person(db, a['person_id'])['name'])}: {word} {money(a['usd'])} $")
    await _edit_q(ctx, r, "…")
    await F.ask_adj(ctx, aid)
    return None


@screen("qp", "full")
async def q_pool(ctx, r: Req):
    pool, day, who = int(r.args[0]), r.args[1], int(r.args[2])
    K.set_pay_day(ctx.db, pool, day, who)
    return await _edit_q(ctx, r, f"✅ {day[8:10]}.{day[5:7]}: {h(P.person(ctx.db, who)['name'])}")


# ───────────────────────── cheklar (kun bo'yicha tuzatish)
@screen("kx", "full")
async def check_days(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    key = r.args[1] if len(r.args) > 1 else None
    if key:
        s, e = K.open_period(db, pid, today(ctx)) if key == "o" else range_of(ctx, key)
        days = db.all("SELECT ch.rd AS rd, COUNT(*) AS n FROM checks ch JOIN reports r ON r.id=ch.report_id "
                      "WHERE r.person_id=? AND r.status='done' AND ch.rd BETWEEN ? AND ? GROUP BY ch.rd "
                      "ORDER BY ch.rd DESC LIMIT 31", (pid, s.isoformat(), e.isoformat()))
        sub = plabel(s, e)
    else:
        days = K.person_days(db, pid, 14)
        sub = r.L("oxirgi kunlar", "последние дни")
    shut = K.closed_days(db, days[-1]["rd"], days[0]["rd"]) if days else set()
    btn = [(f"{'🔒 ' if d['rd'] in shut else ''}{dm(d['rd'])} · {d['n']}", f"kxd:{pid}:{d['rd']}") for d in days]
    rows = grid(btn, 3) + [[(r.L("➕ Chek (bugun)", "➕ Чек (сегодня)"), f"kxa:{pid}:{today(ctx).isoformat()}"),
                            (r.L("📜 Tarix", "📜 История"), f"kh:{pid}:-")],
                           nav(r, f"po:{pid}:{key}" if key else f"po:{pid}")]
    return ui.join(title("🧾", h(p["name"]), r.L("cheklar", "чеки") + f" · {sub}"), "",
                   card([r.L("Kun · cheklar soni. 🔒 — yopilgan kun.", "День · кол-во чеков. 🔒 — закрытый день.")])
                   if days else r.L("<i>Chek yo'q.</i>", "<i>Чеков нет.</i>")), kb(*rows)


@screen("kxd", "full")
async def check_day(ctx, r: Req):
    db = ctx.db
    pid, day = int(r.args[0]), r.args[1]
    if len(r.args) > 2:
        msg = locked(ctx, r, day)
        if msg:
            return msg
        c = K.check_row(db, int(r.args[2]))
        if c and c["acct"] == pid:
            K.toggle_check(db, c["id"])
    p = must(P.person(db, pid))
    cs = K.day_checks(db, pid, day)
    used = sum(1 for c in cs if not c["skip"])
    btn = []
    for c in cs:
        tag = ""
        if c["pay"] and c["pay"] != pid:
            pw = P.person(db, c["pay"])
            tag = f" →{pw['name'][:6]}" if pw else ""
        price = f" {money(c['usd'])}$" if c["usd"] is not None else " ❓"
        btn.append(((("🚫 " if c["skip"] else "✅ ") + num(c["amount"]) + price + tag), f"kxd:{pid}:{day}:{c['id']}"))
    rows = grid(btn, 2)
    rows += grid([(r.L("➕ Chek", "➕ Чек"), f"kxa:{pid}:{day}"), (r.L("✏️ Summa", "✏️ Сумма"), f"kxe:{pid}:{day}"),
                  (r.L("📅 Sana", "📅 Дата"), f"kxm:{pid}:{day}"), (r.L("🗑 Kunni o'chirish", "🗑 Удалить день"),
                                                                   f"kxz:{pid}:{day}")])
    hist = K.history(db, day, pid, 3)
    rows.append([(r.L("📜 Tarix", "📜 История"), f"kh:{pid}:{day}"), (r.L("📅 Kun", "📅 День"), f"kdd:{day}")])
    rows.append(nav(r, f"kx:{pid}"))
    info = [r.L(f"Sanaladi: <b>{used}</b> / {len(cs)}", f"Засчитано: <b>{used}</b> / {len(cs)}"),
            r.L("Chekni bosing: 🚫 sanalmasin / ✅ sanalsin.", "Нажмите на чек: 🚫 не считать / ✅ считать.")]
    if K.is_closed(db, day):
        info.insert(0, r.L("🔒 Kun yopilgan — faqat ega o'zgartira oladi.", "🔒 День закрыт — менять может только владелец."))
    if hist:
        names = {x["id"]: x["name"] for x in db.all("SELECT id, name FROM people")}
        info.append("")
        info += [hist_line(ctx, r, a, names).replace("\n", " · ") for a in hist]
    return ui.join(title("🧾", f"{h(p['name'])} · {day[8:10]}.{day[5:7]}"), "", card(info)), kb(*rows)


@screen("kxa", "full")
async def check_add_ask(ctx, r: Req):
    pid, day = int(r.args[0]), r.args[1]
    msg = locked(ctx, r, day)
    if msg:
        return msg
    ui.ask(r, "check_add", f"kxd:{pid}:{day}", pid=pid, day=day)
    return title("➕", r.L("CHEK", "ЧЕК") + f" · {day[8:10]}.{day[5:7]}") + "\n\n" + card(
        [r.L("Summani yuboring (bir nechta bo'lsa bo'sh joy bilan), masalan <code>1950 2600</code>.",
             "Пришлите сумму (несколько — через пробел), например <code>1950 2600</code>.")]), \
        ui.cancel_kb(r, f"kxd:{pid}:{day}")


@on_input("check_add")
async def check_add(ctx, r: Req, pid: int, day: str):
    msg = locked(ctx, r, day)
    if msg:
        ui.WAIT.pop(r.uid, None)
        return msg
    amounts = K.line_amounts(r.text.replace(",", " "))
    if not amounts:
        return r.L("⚠️ Summa kerak, masalan 1950", "⚠️ Нужна сумма, например 1950")
    for a in amounts:
        K.add_check(ctx.db, pid, day, a)
    r.args = [str(pid), day]
    return await check_day(ctx, r)


@screen("kxe", "full")
async def check_edit_pick(ctx, r: Req):
    pid, day = int(r.args[0]), r.args[1]
    msg = locked(ctx, r, day)
    if msg:
        return msg
    if len(r.args) > 2:
        cid = int(r.args[2])
        ui.ask(r, "check_amount", f"kxd:{pid}:{day}", pid=pid, day=day, cid=cid)
        return title("✏️", r.L("YANGI SUMMA", "НОВАЯ СУММА")) + "\n\n" + card(
            [r.L("Masalan <code>1950</code>.", "Например <code>1950</code>.")]), ui.cancel_kb(r, f"kxd:{pid}:{day}")
    btn = [(num(c["amount"]), f"kxe:{pid}:{day}:{c['id']}") for c in K.day_checks(ctx.db, pid, day)]
    return title("✏️", r.L("Qaysi chek?", "Какой чек?")), kb(*grid(btn, 3), nav(r, f"kxd:{pid}:{day}"))


@on_input("check_amount")
async def check_amount(ctx, r: Req, pid: int, day: str, cid: int):
    v = parse_number(r.text)
    if v is None or v < 1:
        return r.L("⚠️ Summa kerak", "⚠️ Нужна сумма")
    c = K.check_row(ctx.db, cid)
    msg = locked(ctx, r, day, c["rd"] if c else None)
    if msg:
        ui.WAIT.pop(r.uid, None)
        return msg
    if c and c["acct"] == pid:
        K.edit_check_amount(ctx.db, cid, int(v))
    r.args = [str(pid), day]
    return await check_day(ctx, r)


@screen("kxm", "full")
async def check_move(ctx, r: Req):
    pid, day = int(r.args[0]), r.args[1]
    msg = locked(ctx, r, day, r.args[3] if len(r.args) == 4 else None)
    if msg:
        return msg
    if len(r.args) == 3:                                       # chek tanlandi → yangi kun
        cid = int(r.args[2])
        t = today(ctx)
        days = [t - dt.timedelta(days=i) for i in range(6)]
        btn = [(d.strftime("%d.%m"), f"kxm:{pid}:{day}:{cid}:{d.isoformat()}") for d in days]
        return title("📅", r.L("Yangi sana", "Новая дата")), kb(*grid(btn, 3), nav(r, f"kxd:{pid}:{day}"))
    if len(r.args) == 4:
        c = K.check_row(ctx.db, int(r.args[2]))
        if c and c["acct"] == pid:
            K.set_check_day(ctx.db, c["id"], r.args[3])
        r.args = [str(pid), day]
        return await check_day(ctx, r)
    btn = [(num(c["amount"]), f"kxm:{pid}:{day}:{c['id']}") for c in K.day_checks(ctx.db, pid, day)]
    return title("📅", r.L("Qaysi chekning sanasi?", "Дата какого чека?")), kb(*grid(btn, 3), nav(r, f"kxd:{pid}:{day}"))


@screen("kxz", "full")
async def check_day_delete(ctx, r: Req):
    pid, day = int(r.args[0]), r.args[1]
    msg = locked(ctx, r, day)
    if msg:
        return msg
    if len(r.args) > 2:
        K.clear_day(ctx.db, pid, day)
        r.args = [str(pid)]
        return await check_days(ctx, r)
    p = must(P.person(ctx.db, pid))
    return title("🗑", f"{h(p['name'])} · {day[8:10]}.{day[5:7]}") + "\n\n" + card(
        [r.L("Shu kunning HAMMA cheklari o'chirilsinmi?", "Удалить ВСЕ чеки за этот день?")]), \
        kb([(r.L("✅ Ha", "✅ Да"), f"kxz:{pid}:{day}:y"), (r.L("✖️ Yo'q", "✖️ Нет"), f"kxd:{pid}:{day}")])


# ───────────────────────── kim ishladi (zp boshqa odamga, kassa joyida qoladi)
@screen("kw", "full")
async def who_worked(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    if len(r.args) == 1:
        days = K.person_days(db, pid, 10)
        btn = [(f"{d['rd'][8:10]}.{d['rd'][5:7]} · {d['n']}", f"kw:{pid}:{d['rd']}") for d in days]
        return ui.join(title("🔁", h(p["name"]), r.L("kim ishladi — qaysi kun?", "кто работал — какой день?")), "",
                       card([r.L("Kassa va cheklar akkauntda qoladi. Faqat zp ishlagan odamga o'tadi (o'z foizi bilan).",
                                 "Касса и чеки остаются на аккаунте. Зп получает тот, кто работал (по своему проценту).")])), \
            kb(*grid(btn, 3), nav(r, f"po:{pid}"))
    day = r.args[1]
    if len(r.args) == 3:
        msg = locked(ctx, r, day)
        if msg:
            return msg
        who = int(r.args[2])
        K.set_pay_day(db, pid, day, who or None)
        await ui.toast(ctx.bot, r.chat_id, f"✅ {day[8:10]}.{day[5:7]}: " +
                       (h(P.person(db, who)["name"]) if who else r.L("akkaunt egasi", "владелец аккаунта")))
        r.args = [str(pid)]
        from .panel_people import person_card
        return await person_card(ctx, r)
    btn = [(o["name"], f"kw:{pid}:{day}:{o['id']}") for o in K.kassa_people(db, kinds=("worker", "self"))
           if o["id"] != pid]
    if p["kassa_kind"] != "pool":
        btn.append((r.L("↩️ Akkaunt egasi", "↩️ Владелец аккаунта"), f"kw:{pid}:{day}:0"))
    return title("🔁", f"{h(p['name'])} · {day[8:10]}.{day[5:7]}", r.L("kim ishladi?", "кто работал?")), \
        kb(*grid(btn), nav(r, f"kw:{pid}"))


# ───────────────────────── zp o'tkazish (kunlik zp dan %)
@screen("kt", "full")
async def transfer(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    a = r.args
    if len(a) == 1:
        t = today(ctx)
        btn = [((t - dt.timedelta(days=i)).strftime("%d.%m"), f"kt:{pid}:{(t - dt.timedelta(days=i)).isoformat()}")
               for i in range(6)]
        hist = []
        for tr in K.person_transfers(db, pid):
            mark = "✖️" if tr["cancelled"] else "✅"
            f_, t_ = P.person(db, tr["from_id"]), P.person(db, tr["to_id"])
            hist.append((f"{mark} {tr['day'][8:10]}.{tr['day'][5:7]} {f_['name']}→{t_['name']} {tr['pct']:g}%",
                         f"ktc:{pid}:{tr['id']}"))
        rows = grid(btn, 3) + [[x] for x in hist] + [nav(r, f"po:{pid}")]
        return ui.join(title("🔀", h(p["name"]), r.L("zp o'tkazish — qaysi kun?", "перенос зп — за какой день?")), "",
                       card([r.L("Tanlangan kundagi zp ning bir qismi boshqa odamga o'tadi. Pastda — oldingilar "
                                 "(bosing — bekor/qaytarish).",
                                 "Часть зп за выбранный день переходит другому. Ниже — прошлые (нажмите — "
                                 "отменить/вернуть).")])), kb(*rows)
    day = a[1]
    base = K.day_zp(db, pid, day)
    if len(a) == 2:
        if base <= 0:
            return r.L(f"⚠️ {day[8:10]}.{day[5:7]} kuni zp yo'q", f"⚠️ За {day[8:10]}.{day[5:7]} зп нет")
        btn = [(o["name"], f"kt:{pid}:{day}:{o['id']}") for o in P.people(db, kinds=("worker", "self", "partner"))
               if o["id"] != pid and (r.owner or o["kassa_kind"] == "worker")]
        return title("🔀", f"{h(p['name'])} · {day[8:10]}.{day[5:7]}",
                     r.L(f"zp {money(base)} $ — kimga?", f"зп {money(base)} $ — кому?")), kb(*grid(btn), nav(r, f"kt:{pid}"))
    to = int(a[2])
    if len(a) == 3:
        btn = [(f"{x}%", f"kt:{pid}:{day}:{to}:{x}") for x in (100, 75, 50, 25)]
        ui.ask(r, "transfer_pct", f"kt:{pid}", pid=pid, day=day, to=to)
        return title("🔀", f"→ {h(P.person(db, to)['name'])}", r.L("necha foiz? (yoki sonni yozing)",
                                                                    "сколько процентов? (или напишите число)")), \
            kb(*grid(btn, 4), nav(r, f"kt:{pid}"))
    msg = locked(ctx, r, day)
    if msg:
        return msg
    K.add_transfer(db, day, pid, to, float(a[3]))
    ui.WAIT.pop(r.uid, None)
    r.args = [str(pid)]
    return await transfer(ctx, r)


@on_input("transfer_pct")
async def transfer_pct(ctx, r: Req, pid: int, day: str, to: int):
    v = parse_number(r.text)
    if v is None or not 0 < v <= 100:
        return r.L("⚠️ 1 dan 100 gacha", "⚠️ От 1 до 100")
    msg = locked(ctx, r, day)
    if msg:
        ui.WAIT.pop(r.uid, None)
        return msg
    K.add_transfer(ctx.db, day, pid, to, v)
    r.args = [str(pid)]
    return await transfer(ctx, r)


@screen("ktc", "full")
async def transfer_toggle(ctx, r: Req):
    tr = ctx.db.one("SELECT day FROM transfers WHERE id=?", (int(r.args[1]),))
    msg = locked(ctx, r, tr["day"] if tr else None)
    if msg:
        return msg
    K.transfer_toggle(ctx.db, int(r.args[1]))
    r.args = [r.args[0]]
    return await transfer(ctx, r)


# ───────────────────────── 🧮 Haftani hisoblash (foizlar har hafta bir marta tasdiqlanadi)
def wk(arg: str | None, ctx) -> dt.date:
    if arg:
        try:
            return K.week_start(dt.date.fromisoformat(arg))
        except ValueError:
            pass
    t = today(ctx)
    cur = K.week_start(t)
    prev = cur - dt.timedelta(days=7)
    has_prev = ctx.db.one("SELECT 1 FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' "
                          "AND ch.rd BETWEEN ? AND ? LIMIT 1", (prev.isoformat(), (cur - dt.timedelta(days=1)).isoformat()))
    return prev if has_prev and not K.week_confirmed(ctx.db, prev) else cur


def wlabel(w: dt.date) -> str:
    return plabel(w, w + dt.timedelta(days=6))


def pc(v) -> str:
    return "❓" if v is None or v == 0 else f"{float(v):g}%"


def rule_lines(r: Req, w: dict, names: dict, partner: str) -> list[str]:
    you = r.L("Siz", "Вы")
    out = []
    for it in w["accts"]:
        miss = (it["pid"], "acct") in w["missing"]
        head = f"<b>{h(it['name'])}</b>"
        if it["kind"] == "pool":
            head += f" <i>({r.L('umumiy', 'общий')})</i>"
        elif it["kind"] == "self":
            head += f" <i>({you.lower()})</i>"
        head += f" · {money(it['usd'])} $" + (" ❓" if miss else "")
        if it["kind"] == "worker":
            rest = 100 - (it["wpct"] or 0) - (it["opct"] or 0) - it["kshare"]
            parts = [f"{h(it['name'])} {pc(it['wpct'])}" if it["zp_on"] else
                     f"{h(it['name'])} <i>{r.L('zp o‘zingiz', 'зп сами')}</i>",
                     f"{you} {pc(it['opct']) if it['opct'] is not None else '❓'}"]
        elif it["kind"] == "self":
            rest = 100 - (it["wpct"] or 0) - it["kshare"]
            parts = [f"{you} {pc(it['wpct'])}"]
        else:
            rest = None
            parts = [r.L("ishlagan xodim — o‘z %", "кто работал — свой %"),
                     f"{you} {pc(it['opct']) if it['opct'] is not None else '❓'}"]
        if it["kshare_owner"]:
            parts[-1] += f" <i>(−{r.L('ulush', 'доля')} {it['kshare_owner']:g}%)</i>"
        if it["kshare"]:
            parts.append(f"{r.L('ulush', 'доля')} {it['kshare']:g}% <i>({h(partner)}{r.L('dan', '')})</i>")
        if rest is None:
            parts.append(f"{h(partner)} {r.L('qolgani', 'остаток')}")
        elif miss:
            parts.append(f"{h(partner)} {r.L('qolgani', 'остаток')}")
        else:
            parts.append(f"{h(partner)} <b>{rest:g}%</b>" + (" ⚠️" if rest < 0 else ""))
        out.append(head)
        out.append("   " + " · ".join(parts))
    for it in w["subs"]:
        out.append(f"<b>{h(it['name'])}</b> — {pc(it['wpct'])} <i>({r.L('boshqa akkauntda ishladi', 'работал на другом аккаунте')})</i>")
    return out


def share_payer(r: Req, sh, names: dict, partner: str) -> str:
    if sh["mode"] == "deduct":
        return r.L(f"{names.get(sh['from_id'], '?')}dan ushlanadi", f"удерживается у {names.get(sh['from_id'], '?')}")
    if sh["mode"] == "partner":
        return r.L(f"{partner} to'laydi", f"платит {partner}")
    return r.L("siz to'laysiz", "платите вы")


def share_line(r: Req, sh, names: dict, partner: str) -> str:
    base = r.L("kassasidan", "от кассы") if sh["base"] == "kassa" else r.L("oyligidan", "от зп")
    fr, to = h(names.get(sh["from_id"], "?")), h(names.get(sh["to_id"], "?"))
    return f"{fr} {base} <b>{sh['pct']:g}%</b> → {to} · <i>{h(share_payer(r, sh, names, partner))}</i>"


def partner_name(ctx) -> str:
    p = ctx.db.one("SELECT name FROM people WHERE kassa_kind='partner' AND active=1 LIMIT 1")
    return p["name"] if p else "Artur"


@screen("kz", "owner")
async def week_calc(ctx, r: Req):
    db = ctx.db
    w0 = wk(r.args[0] if r.args else None, ctx)
    w = K.week_rules(db, w0)
    names = {p["id"]: p["name"] for p in db.all("SELECT id, name FROM people")}
    partner = partner_name(ctx)
    t = today(ctx)
    if w["confirmed"]:
        row = db.one("SELECT ts FROM weeks WHERE week=?", (w0.isoformat(),))
        status = f"✅ {r.L('Hisoblangan', 'Рассчитана')} · {dt.datetime.fromtimestamp(row['ts'], ctx.tz):%d.%m %H:%M}"
    else:
        status = f"⏳ {r.L('Hali hisoblanmagan', 'Ещё не рассчитана')}"
    if w0 + dt.timedelta(days=6) >= t:
        status += r.L(" · hafta tugamagan", " · неделя не закончилась")
    parts = [title("🧮", r.L("HAFTANI HISOBLASH", "РАСЧЁТ НЕДЕЛИ"), f"{wlabel(w0)} · {status}")]
    btn = []
    if not w["accts"] and not w["subs"]:
        parts.append(r.L("<i>Bu haftada chek yo'q.</i>", "<i>За эту неделю чеков нет.</i>"))
    else:
        lines = [f"<b>📐 {r.L('Foizlar', 'Проценты')}</b>"
                 + ("" if w["confirmed"] else f" · <i>{r.L('o‘tgan haftadagidek', 'как на прошлой неделе')}</i>")]
        lines += rule_lines(r, w, names, partner)
        parts.append(card(lines))
        btn = [(f"✏️ {it['name']}", f"kze:{w0.isoformat()}:{it['pid']}") for it in w["accts"] + w["subs"]]
    if w["shares"]:
        parts.append(card([f"<b>🤝 {r.L('Ulushlar', 'Доли')}</b>"] + [share_line(r, sh, names, partner)
                                                                    for sh in w["shares"]]))
    hint = []
    if w["missing"]:
        hint.append(r.L(f"❓ {len(w['missing'])} ta foiz kiritilmagan — «✅ Hisoblash» ni bosing, bot o'zi so'raydi.",
                        f"❓ Не введено процентов: {len(w['missing'])} — нажмите «✅ Рассчитать», бот спросит."))
    if w["over"]:
        hint.append("⚠️ " + ", ".join(h(names.get(x, "?")) for x in w["over"]) +
                    r.L(" — foizlar 100% dan oshdi", " — сумма процентов больше 100%"))
    hint.append(r.L("To'g'ri bo'lsa — «✅». O'zgargan bo'lsa — ismni bosib yangi sonni yozing. O'zgarish faqat shu "
                    "haftadan: o'tgan haftalar buzilmaydi.",
                    "Всё верно — «✅». Изменилось — нажмите имя и напишите число. Меняется только с этой недели: "
                    "прошлые недели не трогаются."))
    parts.append(card(hint))
    rows = grid(btn, 3)
    rows.append([(r.L("🤝 Ulushlar", "🤝 Доли"), f"kzs:{w0.isoformat()}")])
    if w["accts"] or w["subs"]:
        rows.append([((r.L("🔄 Qayta hisoblash", "🔄 Пересчитать") if w["confirmed"] else
                       r.L("✅ O'zgarmadi — hisoblash", "✅ Без изменений — рассчитать")), f"kzy:{w0.isoformat()}")])
    if w["confirmed"]:
        rows.append([(r.L("📊 Natija", "📊 Итог"), f"kr:{w0.isoformat()}_{(w0 + dt.timedelta(days=6)).isoformat()}"),
                     (r.L("📋 To'lov ro'yxati", "📋 Ведомость"), f"kpay:{w0.isoformat()}")])
    prev, nxt = w0 - dt.timedelta(days=7), w0 + dt.timedelta(days=7)
    navw = [(f"‹ {dm(prev)}", f"kz:{prev.isoformat()}")]
    if nxt <= K.week_start(t):
        navw.append((f"{dm(nxt)} ›", f"kz:{nxt.isoformat()}"))
    rows.append(navw)
    rows.append([(r.L("⚙️ Zp hisoblash usuli", "⚙️ Режим расчёта зп"), "kzm")])
    rows.append(nav(r, "k"))
    return clip(ui.join(*parts)), kb(*rows)


def _rule_item(w: dict, pid: int):
    return next((x for x in w["accts"] + w["subs"] if x["pid"] == pid), None)


@screen("kze", "owner")
async def week_edit(ctx, r: Req):
    w0 = K.week_start(dt.date.fromisoformat(r.args[0]))
    pid = int(r.args[1])
    return week_ask(ctx, r, w0, pid)


def week_ask(ctx, r: Req, w0: dt.date, pid: int, note: str = ""):
    w = K.week_rules(ctx.db, w0)
    it = must(_rule_item(w, pid))
    partner = partner_name(ctx)
    ui.ask(r, "week_pct", f"kz:{w0.isoformat()}", week=w0.isoformat(), pid=pid, kind=it["kind"])
    nm = h(it["name"])
    if it["kind"] == "worker":
        cur = f"{pc(it['wpct'])} · {r.L('siz', 'вы')} {pc(it['opct']) if it['opct'] is not None else '❓'}"
        ask = r.L(f"Ikki son yozing: <b>{nm} foizi</b> va <b>sizning foizingiz</b>. Qolgani — {h(partner)}ga.\n"
                  f"Masalan: <code>41 14</code>",
                  f"Напишите два числа: <b>процент {nm}</b> и <b>ваш процент</b>. Остаток — {h(partner)}.\n"
                  f"Например: <code>41 14</code>")
    elif it["kind"] == "self":
        cur = pc(it["wpct"])
        ask = r.L(f"O'z akkauntingizdan <b>sizning foizingiz</b>. Qolgani — {h(partner)}ga. Masalan: <code>50</code>",
                  f"<b>Ваш процент</b> с вашего аккаунта. Остаток — {h(partner)}. Например: <code>50</code>")
    elif it["kind"] == "pool":
        cur = pc(it["opct"]) if it["opct"] is not None else "❓"
        ask = r.L(f"Umumiy akkauntdan <b>sizning foizingiz</b>. Ishlagan xodim o'z foizini oladi, qolgani — "
                  f"{h(partner)}ga. Masalan: <code>10</code>",
                  f"<b>Ваш процент</b> с общего аккаунта. Кто работал — получает свой %, остаток — {h(partner)}. "
                  f"Например: <code>10</code>")
    else:
        cur = pc(it["wpct"])
        ask = r.L(f"<b>{nm} foizi</b> (boshqa akkauntda ishlaganda). Masalan: <code>41</code>",
                  f"<b>Процент {nm}</b> (когда работает на другом аккаунте). Например: <code>41</code>")
    lines = ([note] if note else []) + [f"{r.L('Hozir', 'Сейчас')}: {cur}", ask,
                                        f"<i>{r.L('Shu haftadan boshlab', 'С этой недели')} ({wlabel(w0)})</i>"]
    return ui.join(title("✏️", nm, wlabel(w0)), "", card(lines)), ui.cancel_kb(r, f"kz:{w0.isoformat()}")


@on_input("week_pct", "owner")
async def week_pct_set(ctx, r: Req, week: str, pid: int, kind: str):
    db = ctx.db
    w0 = dt.date.fromisoformat(week)
    nums = [parse_number(x) for x in r.text.replace(",", " ").replace("%", " ").split()]
    need = 2 if kind == "worker" else 1
    if len(nums) != need or any(v is None or not 0 <= v <= 100 for v in nums):
        return r.L("⚠️ Masalan: 41 14", "⚠️ Например: 41 14") if need == 2 else r.L("⚠️ Masalan: 41", "⚠️ Например: 41")
    nums = [float(v or 0) for v in nums]
    w = K.week_rules(db, w0)
    it = _rule_item(w, pid)
    kshare = it["kshare"] if it and "kshare" in it else 0.0
    if kind in ("worker", "self") and sum(nums) + kshare > 100:
        return r.L("⚠️ Jami 100% dan oshib ketdi", "⚠️ В сумме больше 100%")
    if kind == "worker":
        K.set_percent(db, pid, nums[0], w0)
        K.set_owner_pct(db, pid, nums[1], w0)
    elif kind == "self":
        K.set_percent(db, pid, nums[0], w0)
        K.set_owner_pct(db, pid, 0, w0)
    elif kind == "pool":
        K.set_owner_pct(db, pid, nums[0], w0)
    else:
        K.set_percent(db, pid, nums[0], w0)
    ui.WAIT.pop(r.uid, None)
    w = K.week_rules(db, w0)
    if w["missing"]:
        nxt = w["missing"][0][0]
        return week_ask(ctx, r, w0, nxt, r.L(f"❓ Keyingisi: {h(_rule_item(w, nxt)['name'])}",
                                             f"❓ Следующий: {h(_rule_item(w, nxt)['name'])}"))
    r.args = [w0.isoformat()]
    return await week_calc(ctx, r)


@screen("kzy", "owner")
async def week_confirm(ctx, r: Req):
    db = ctx.db
    w0 = K.week_start(dt.date.fromisoformat(r.args[0]))
    w = K.week_rules(db, w0)
    if w["missing"]:
        pid = w["missing"][0][0]
        return week_ask(ctx, r, w0, pid, r.L(f"❓ {h(_rule_item(w, pid)['name'])} — foiz kerak",
                                             f"❓ {h(_rule_item(w, pid)['name'])} — нужен процент"))
    if w["over"]:
        return r.L("⚠️ Foizlar 100% dan oshgan — tuzating", "⚠️ Проценты больше 100% — исправьте")
    K.confirm_week(db, w0)
    await ui.toast(ctx.bot, r.chat_id, r.L(f"✅ Hafta {wlabel(w0)} hisoblandi", f"✅ Неделя {wlabel(w0)} рассчитана"))
    return report_show(ctx, r, f"{w0.isoformat()}_{(w0 + dt.timedelta(days=6)).isoformat()}")


@screen("kzm", "owner")
async def zp_mode_screen(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] in K.ZP_MODES:
        db.set("zp_mode", r.args[0])
    mode = K.zp_mode(db)
    opts = [("button", r.L("🧮 Tugma bilan", "🧮 По кнопке"),
             r.L("hafta tugagach «Haftani hisoblash» — foizlarni tasdiqlaysiz, keyin zp chiqadi",
                 "в конце недели «Рассчитать неделю» — подтверждаете проценты, потом видна зп")),
            ("auto", r.L("⚡ Avtomatik", "⚡ Автоматически"),
             r.L("zp doim ko'rinadi, oxirgi kiritilgan foizlar bilan", "зп видна всегда, по последним процентам")),
            ("off", r.L("⛔ O'chiq", "⛔ Выключено"),
             r.L("bot zp hisoblamaydi — faqat kassa, jarima, bonus, avans; o'zingiz hisoblaysiz",
                 "бот не считает зп — только касса, штрафы, бонусы, авансы; считаете сами"))]
    lines = [f"{'🔘' if k == mode else '⚪'} <b>{t}</b> — {d}" for k, t, d in opts]
    rows = [[((("✅ " if k == mode else "") + t), f"kzm:{k}")] for k, t, _d in opts]
    rows.append(nav(r, "kz"))
    return ui.join(title("⚙️", r.L("ZP HISOBLASH USULI", "РЕЖИМ РАСЧЁТА ЗП")), "", card(lines)), kb(*rows)


# ───────────────────────── 🤝 ulushlar (haftalik: o'zgarish shu haftadan boshlab)
@screen("ksh", "owner")
async def shares(ctx, r: Req):
    pid = int(r.args[0]) if r.args else 0
    return share_list(ctx, r, K.week_start(today(ctx)), pid)


@screen("kzs", "owner")
async def week_shares(ctx, r: Req):
    w0 = K.week_start(dt.date.fromisoformat(r.args[0]))
    pid = int(r.args[1]) if len(r.args) > 1 else 0
    return share_list(ctx, r, w0, pid)


def share_list(ctx, r: Req, w0: dt.date, pid: int = 0):
    db = ctx.db
    names = {p["id"]: p["name"] for p in db.all("SELECT id, name FROM people")}
    partner = partner_name(ctx)
    items = K.shares(db, pid or None, w0)
    lines = [share_line(r, sh, names, partner) for sh in items]
    btn = [[(f"✏️ {names.get(sh['from_id'], '?')} → {names.get(sh['to_id'], '?')} {sh['pct']:g}%",
             f"kzse:{w0.isoformat()}:{sh['id']}")] for sh in items]
    rows = btn + [[(r.L("➕ Yangi ulush", "➕ Новая доля"), f"kzsa:{w0.isoformat()}")],
                  nav(r, f"po:{pid}" if pid else f"kz:{w0.isoformat()}")]
    note = r.L("Masalan: «Baxa oyligidan 5% → Bayzed · Baxadan ushlanadi». O'zgarish shu haftadan boshlab "
               f"({wlabel(w0)}), o'tgan haftalar o'zgarmaydi.",
               "Например: «Baxa от зп 5% → Bayzed · удерживается у Baxa». Изменение — с этой недели "
               f"({wlabel(w0)}), прошлые недели не меняются.")
    return ui.join(title("🤝", r.L("ULUSHLAR", "ДОЛИ"), wlabel(w0)), "", card(lines) if lines else
                   r.L("<i>Ulush yo'q.</i>", "<i>Долей нет.</i>"), card([note])), kb(*rows)


@screen("kzsa", "owner")
async def share_add(ctx, r: Req):
    db = ctx.db
    w0 = K.week_start(dt.date.fromisoformat(r.args[0]))
    a = r.args[1:]
    ws = w0.isoformat()
    ppl = P.people(db, kinds=("worker", "self", "partner", "pool"))
    back = f"kzs:{ws}"
    if not a:
        btn = [(p["name"], f"kzsa:{ws}:{p['id']}") for p in ppl if p["kassa_kind"] in ("worker", "self", "partner")]
        return title("🤝", r.L("YANGI ULUSH", "НОВАЯ ДОЛЯ"), r.L("1/3 · kim oladi?", "1/3 · кто получает?")), \
            kb(*grid(btn), nav(r, back))
    to = int(a[0])
    if len(a) == 1:
        btn = [(p["name"], f"kzsa:{ws}:{to}:{p['id']}") for p in ppl if p["id"] != to
               and p["kassa_kind"] in ("worker", "pool", "self")]
        return title("🤝", r.L("YANGI ULUSH", "НОВАЯ ДОЛЯ"), r.L("2/3 · kimdan?", "2/3 · от кого?")), \
            kb(*grid(btn), nav(r, f"kzsa:{ws}"))
    fr = int(a[1])
    if len(a) == 2:
        fp = must(P.person(db, fr))
        opts = [(r.L("💰 Oyligidan", "💰 От зп"), f"kzsa:{ws}:{to}:{fr}:zp"),
                (r.L("💵 Kassasidan", "💵 От кассы"), f"kzsa:{ws}:{to}:{fr}:kassa")]
        if fp["kassa_kind"] == "pool":
            opts = opts[1:]
        return title("🤝", f"{h(fp['name'])} → {h(P.person(db, to)['name'])}", r.L("3/3 · nimadan?", "3/3 · от чего?")), \
            kb(opts, nav(r, f"kzsa:{ws}:{to}"))
    base = a[2] if a[2] in ("zp", "kassa") else "zp"
    ui.ask(r, "wshare_pct", back, week=ws, to=to, fr=fr, base=base)
    word = r.L("oyligidan", "от зп") if base == "zp" else r.L("kassasidan", "от кассы")
    return title("🤝", r.L("NECHA FOIZ?", "СКОЛЬКО ПРОЦЕНТОВ?")) + "\n\n" + card(
        [f"{h(P.person(db, fr)['name'])} {word} → {h(P.person(db, to)['name'])}",
         r.L("Sonni yuboring, masalan <code>5</code>.", "Пришлите число, например <code>5</code>.")]), \
        ui.cancel_kb(r, back)


@on_input("wshare_pct", "owner")
async def share_pct(ctx, r: Req, week: str, to: int, fr: int, base: str):
    v = parse_number(r.text.replace("%", ""))
    if v is None or not 0 < v <= 100:
        return r.L("⚠️ 1 dan 100 gacha", "⚠️ От 1 до 100")
    fk = (P.person(ctx.db, fr) or {"kassa_kind": ""})["kassa_kind"]
    mode = "deduct" if base == "zp" else "owner"
    if fk == "pool" or (base == "kassa" and fk == "self"):
        mode = "owner"
    sid = K.add_share(ctx.db, to, fr, v, base, mode, week)
    ui.WAIT.pop(r.uid, None)
    r.args = [week, str(sid)]
    return await share_edit(ctx, r)


@screen("kzse", "owner")
async def share_edit(ctx, r: Req):
    db = ctx.db
    w0 = K.week_start(dt.date.fromisoformat(r.args[0]))
    ws = w0.isoformat()
    sid = int(r.args[1])
    sh = must(K.share(db, sid))
    if len(r.args) > 2:
        op = r.args[2]
        if op == "b":
            sid = K.share_change(db, sid, w0, base="zp" if sh["base"] == "kassa" else "kassa")
        elif op == "m":
            cyc = {"deduct": "owner", "owner": "partner", "partner": "deduct"}
            sid = K.share_change(db, sid, w0, mode=cyc.get(sh["mode"], "owner"))
        elif op == "x":
            K.end_share(db, sid, w0)
            return share_list(ctx, r, w0)
        sh = must(K.share(db, sid))
    names = {p["id"]: p["name"] for p in db.all("SELECT id, name FROM people")}
    ui.ask(r, "wshare_set", f"kzs:{ws}", week=ws, sid=sid)
    lines = [share_line(r, sh, names, partner_name(ctx)),
             r.L(f"Amal qiladi: {dm(sh['from_day'])} dan", f"Действует с {dm(sh['from_day'])}")
             if sh["from_day"] > "2000-01-01" else None]
    return ui.join(title("🤝", r.L("ULUSH", "ДОЛЯ"), wlabel(w0)), "", card(lines),
                   r.L("<i>Foizni o'zgartirish uchun sonni yozing.</i>", "<i>Чтобы изменить процент — напишите число.</i>")), \
        kb([(r.L("🔄 Oyligidan ↔ kassasidan", "🔄 От зп ↔ от кассы"), f"kzse:{ws}:{sid}:b")],
           [(r.L("💳 Kim to'laydi (almashtirish)", "💳 Кто платит (сменить)"), f"kzse:{ws}:{sid}:m")],
           [(r.L("🗑 Shu haftadan o'chirish", "🗑 Убрать с этой недели"), f"kzse:{ws}:{sid}:x")], nav(r, f"kzs:{ws}"))


@on_input("wshare_set", "owner")
async def share_set_pct(ctx, r: Req, week: str, sid: int):
    v = parse_number(r.text.replace("%", ""))
    if v is None or not 0 < v <= 100:
        return r.L("⚠️ 1 dan 100 gacha", "⚠️ От 1 до 100")
    sid = K.share_change(ctx.db, sid, dt.date.fromisoformat(week), pct=v)
    ui.WAIT.pop(r.uid, None)
    r.args = [week, str(sid)]
    return await share_edit(ctx, r)
