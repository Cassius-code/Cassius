"""👥 Xodimlar: ro'yxat, kabinet (kassa + zp + jarima/bonus), sozlamalar, oylik berildi, xodimga yuborish."""
from __future__ import annotations

import datetime as dt

from . import kassa as K
from . import people as P
from . import ui
from .kassa_view import label as plabel, money, owner_cabinet, person_view, worker_message
from .timeutil import local_date, parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title, must

KIND_ICON = {"self": "👑", "partner": "🤝", "pool": "🔁", "worker": "💼", "": "👤"}
DAYS_UZ = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def kind_name(r: Req, kind: str) -> str:
    return {"self": r.L("ega (siz)", "владелец (вы)"), "partner": r.L("hamkor", "партнёр"),
            "pool": r.L("umumiy akkaunt", "общий аккаунт"), "worker": r.L("kassa xodimi", "обработчик"),
            "": r.L("faqat nazorat", "только контроль")}[kind]


def visible(r: Req, p) -> bool:
    return r.owner or p["kassa_kind"] not in ("self", "partner")


def today(ctx) -> dt.date:
    return local_date(ctx.clock(), ctx.tz)


@screen("p", "view")
async def people_list(ctx, r: Req):
    db = ctx.db
    archived = bool(r.args and r.args[0] == "a")
    ps = [p for p in P.people(db, active_only=False) if bool(p["active"]) != archived and visible(r, p)]
    btn = []
    for p in ps:
        folders = ", ".join(f["name"] for f in P.person_folders(db, p["id"]))
        tag = f" · {folders}" if folders else ""
        btn.append((f"{KIND_ICON.get(p['kassa_kind'], '👤')} {p['name']}{tag}"[:40], f"po:{p['id']}"))
    rows = grid(btn)
    if r.can("full") and not archived:
        rows.append([(r.L("➕ Yangi xodim", "➕ Новый сотрудник"), "pn"), (r.L("🗄 Arxiv", "🗄 Архив"), "p:a")])
    rows.append(nav(r, "p" if archived else "m"))
    legend = r.L("👑 ega · 💼 kassa xodimi · 🔁 umumiy akkaunt · 🤝 hamkor · 👤 faqat nazorat",
                 "👑 владелец · 💼 обработчик · 🔁 общий аккаунт · 🤝 партнёр · 👤 только контроль")
    head = title("👥", r.L("XODIMLAR", "СОТРУДНИКИ") + (r.L(" · ARXIV", " · АРХИВ") if archived else ""))
    body = card([legend]) if ps else r.L("<i>Hozircha hech kim yo'q.</i>", "<i>Пока никого нет.</i>")
    return ui.join(head, "", body), kb(*rows)


# ───────────────────────── yangi xodim
@screen("pn", "full")
async def new_ask(ctx, r: Req):
    fid = int(r.args[0]) if r.args else 0
    ui.ask(r, "person_new", "p", fid=fid)
    return title("➕", r.L("YANGI XODIM", "НОВЫЙ СОТРУДНИК")) + "\n\n" + card(
        [r.L("Ism va @username yuboring, masalan <code>Bayzed @bayzed</code>. Faqat ism ham bo'ladi.",
             "Пришлите имя и @username, например <code>Bayzed @bayzed</code>. Можно только имя.")]), \
        ui.cancel_kb(r, "p")


@on_input("person_new")
async def new_person(ctx, r: Req, fid: int = 0):
    import re
    text = r.text.strip()
    m = re.search(r"@([A-Za-z0-9_]{4,32})", text)
    username = m.group(1) if m else ""
    name = re.sub(r"@[A-Za-z0-9_]+", "", text).strip() or username
    if not name:
        return r.L("⚠️ Ism yuboring", "⚠️ Пришлите имя")
    if username and P.by_username(ctx.db, username):
        return r.L("⚠️ Bu @username allaqachon bor", "⚠️ Такой @username уже есть")
    pid = P.add_person(ctx.db, name, username)
    if fid:
        P.toggle_folder_person(ctx.db, fid, pid)
    if ctx.userbot is not None and ctx.userbot.state == "online" and username:
        ui.bg(ctx.userbot.resolve_people())
    r.args = [str(pid)]
    return await person_card(ctx, r)


# ───────────────────────── kabinet
def period_of(ctx, r: Req, pid: int, key: str | None):
    t = today(ctx)
    if not key or key == "o":
        s, e = K.open_period(ctx.db, pid, t)
        return s, e, "o"
    s, e = K.period_range(key, t)
    return s, e, key


@screen("po", "view")
async def person_card(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = P.person(db, pid)
    if p is None or not visible(r, p):
        return await people_list(ctx, r)
    key = r.args[1] if len(r.args) > 1 else None
    s, e, key = period_of(ctx, r, pid, key)
    zst = K.zp_state(db, s, e, today(ctx))
    if p["kassa_kind"] == "self" and r.owner:
        b = K.calc(db, s, e)
        text = owner_cabinet(b, s, e, r.lang, b["rows"].get(pid), zst)
        rows = grid([(r.L("📅 Davr", "📅 Период"), f"pp:{pid}"), (r.L("🧾 Cheklar", "🧾 Чеки"), f"kx:{pid}"),
                     (r.L("⚠️ Jarima / bonus", "⚠️ Штраф / бонус"), f"pa:{pid}"),
                     (r.L("⚙️ Sozlamalar", "⚙️ Настройки"), f"ps:{pid}")])
        rows.append(nav(r, "p"))
        return text, kb(*rows)
    folders = ", ".join(f["name"] for f in P.person_folders(db, pid))
    info = [f"{KIND_ICON.get(p['kassa_kind'], '👤')} {kind_name(r, p['kassa_kind'])}"
            + (f" · <b>{K.percent_on(db, pid, today(ctx)):g}%</b>" if p["kassa_kind"] in ("worker", "self", "partner")
               else ""),
            (f"📁 {h(folders)}" if folders else None),
            (f"✈️ @{h(p['username'])}" if p["username"] else None) or (f"🆔 {p['tg_id']}" if p["tg_id"] else None)]
    if p["kassa_kind"] in ("worker", "self"):
        info.append(f"💰 {r.L('Zp hisoblash', 'Расчёт зп')} — {onoff(r, p['zp_on'])}")
    lp = K.last_payout(db, pid)
    if lp is not None:
        info.append(f"✅ {r.L('Oxirgi oylik', 'Последняя зп')}: {dt.date.fromisoformat(lp['upto_day']):%d.%m}"
                    + (f" · {money(lp['total'])} $" if lp["total"] is not None and r.can("full") else ""))
    period = r.L("joriy davr", "текущий период") if key == "o" else ""
    parts = [title(KIND_ICON.get(p["kassa_kind"], "👤"), h(p["name"].upper()), f"{plabel(s, e)} {period}".strip()), "",
             card(info)]
    row = None
    if p["kassa_kind"] and r.can("view"):
        b = K.calc(db, s, e)
        row = b["rows"].get(pid)
        if row is not None:
            parts.append(person_view(b, row, s, e, r.lang, r.owner, zst["ready"]))
    else:
        adjs = K.person_adjs(db, pid, s, e)
        if adjs:
            parts.append(card([f"{'−' if a['kind'] != 'bonus' else '+'} {money(a['usd'])} $ · {a['day'][8:10]}."
                               f"{a['day'][5:7]} · {h(a['note'] or a['source'])}" for a in adjs if not a["cancelled"]]))
    att = db.all("SELECT * FROM attendance WHERE person_id=? AND day BETWEEN ? AND ? AND late_min>0 ORDER BY day",
                 (pid, s.isoformat(), e.isoformat()))
    if att:
        parts.append(card([f"🕘 {r.L('Kech qolishlar', 'Опоздания')}: " +
                           ", ".join(f"{a['day'][8:10]}.{a['day'][5:7]} ({a['late_min']} {r.L('daq', 'мин')})"
                                     for a in att)]))
    rows = []
    if r.owner and not zst["ready"] and zst["weeks"] and p["kassa_kind"] in ("worker", "partner", "self"):
        rows += grid([(f"🧮 {plabel(x, x + dt.timedelta(days=6))}", f"kz:{x.isoformat()}") for x in zst["weeks"]], 2)
    if r.can("full"):
        if p["kassa_kind"] != "pool":
            rows += [[(r.L("⚠️ Jarima", "⚠️ Штраф"), f"paf:{pid}"), (r.L("🎁 Bonus", "🎁 Бонус"), f"pab:{pid}"),
                      (r.L("💸 Avans", "💸 Аванс"), f"paa:{pid}") if r.owner else None]]
        rows += grid([(r.L("📋 Jarima/bonuslar", "📋 Штрафы/бонусы"), f"pa:{pid}"), (r.L("📅 Davr", "📅 Период"),
                                                                                      f"pp:{pid}")])
        if p["kassa_kind"] in ("worker", "self", "pool"):
            rows += grid([(r.L("🧾 Cheklar", "🧾 Чеки"), f"kx:{pid}:{key}"), (r.L("🔁 Kim ishladi", "🔁 Кто работал"),
                                                                               f"kw:{pid}")])
        if p["kassa_kind"] in ("worker", "partner"):
            rows += grid([(r.L("🔀 Zp o'tkazish", "🔀 Перенос зп"), f"kt:{pid}")]
                         + ([(r.L("🤝 Ulushlar", "🤝 Доли"), f"ksh:{pid}")] if r.owner else []))
        if p["kassa_kind"] == "worker":
            rows += grid([(r.L("📤 Xodimga yuborish", "📤 Отправить ему"), f"psd:{pid}:{key}")]
                         + ([(r.L("✅ Oylik berildi", "✅ Зп выдана"), f"ppd:{pid}:{key}")] if r.owner else []))
        rows.append([(r.L("⚙️ Sozlamalar", "⚙️ Настройки"), f"ps:{pid}")])
    else:
        rows.append([(r.L("📅 Davr", "📅 Период"), f"pp:{pid}")])
    rows.append(nav(r, "p"))
    return ui.join(*parts), kb(*rows)



@screen("pp", "view")
async def period_pick(ctx, r: Req):
    pid = int(r.args[0])
    p = must(P.person(ctx.db, pid))
    opts = [(r.L("🟢 Joriy (oxirgi oylikdan)", "🟢 Текущий (с последней зп)"), f"po:{pid}:o"),
            (r.L("Bu hafta", "Эта неделя"), f"po:{pid}:tw"), (r.L("O'tgan hafta", "Прошлая неделя"), f"po:{pid}:lw"),
            (r.L("Bu oy", "Этот месяц"), f"po:{pid}:tm"), (r.L("O'tgan oy", "Прошлый месяц"), f"po:{pid}:lm"),
            (r.L("Bugun", "Сегодня"), f"po:{pid}:{today(ctx).isoformat()}")]
    rows = [[opts[0]]] + grid(opts[1:]) + [[(r.L("📆 Sana / oraliq", "📆 Дата / период"), f"ppx:{pid}")], nav(r, f"po:{pid}")]
    return title("📅", h(p["name"]), r.L("qaysi davr?", "какой период?")), kb(*rows)


@screen("ppx", "view")
async def period_ask(ctx, r: Req):
    pid = int(r.args[0])
    ui.ask(r, "person_period", f"po:{pid}", pid=pid)
    return title("📆", r.L("DAVR", "ПЕРИОД")) + "\n\n" + card(
        [r.L("Sana (<code>05.10</code>) yoki oraliq (<code>05.10-11.10</code>) yuboring.",
             "Пришлите дату (<code>05.10</code>) или период (<code>05.10-11.10</code>).")]), ui.cancel_kb(r, f"po:{pid}")


@on_input("person_period", "view")
async def period_set(ctx, r: Req, pid: int):
    ds = K.parse_dates(r.text, today(ctx))
    if not ds:
        return r.L("⚠️ Masalan: 05.10-11.10", "⚠️ Например: 05.10-11.10")
    key = ds[0].isoformat() if len(ds) == 1 else f"{min(ds[:2]).isoformat()}_{max(ds[:2]).isoformat()}"
    r.args = [str(pid), key]
    return await person_card(ctx, r)


# ───────────────────────── jarima / bonus / avans
@screen("paf", "full")
async def adj_fine_ask(ctx, r: Req):
    return adj_ask(ctx, r, "fine")


@screen("pab", "full")
async def adj_bonus_ask(ctx, r: Req):
    return adj_ask(ctx, r, "bonus")


@screen("paa", "owner")
async def adj_adv_ask(ctx, r: Req):
    return adj_ask(ctx, r, "adv")


def adj_ask(ctx, r: Req, kind: str):
    pid = int(r.args[0])
    p = must(P.person(ctx.db, pid))
    ui.ask(r, "adj_add", f"po:{pid}", pid=pid, kind=kind)
    word = {"fine": r.L("JARIMA", "ШТРАФ"), "bonus": r.L("BONUS", "БОНУС"), "adv": r.L("AVANS", "АВАНС")}[kind]
    return title({"fine": "⚠️", "bonus": "🎁", "adv": "💸"}[kind], f"{word} · {h(p['name'])}") + "\n\n" + card(
        [r.L("Summani $ da yuboring, xohlasangiz izoh bilan: <code>5 kech qoldi</code>. Bugungi kunga yoziladi.",
             "Пришлите сумму в $, можно с пояснением: <code>5 опоздал</code>. Запишется на сегодня.")]), \
        ui.cancel_kb(r, f"po:{pid}")


@on_input("adj_add")
async def adj_add(ctx, r: Req, pid: int, kind: str):
    import re
    from .panel_kassa import locked
    if kind == "adv" and not r.owner:
        ui.WAIT.pop(r.uid, None)
        return r.L("⛔ Avansni faqat ega yozadi", "⛔ Аванс записывает только владелец")
    msg = locked(ctx, r, today(ctx).isoformat())
    if msg:
        ui.WAIT.pop(r.uid, None)
        return msg
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*\$?\s*(.*)$", r.text, re.S)
    if not m or float(m.group(1).replace(",", ".")) <= 0:
        return r.L("⚠️ Summa kerak, masalan 5", "⚠️ Нужна сумма, например 5")
    K.add_adj(ctx.db, pid, kind, float(m.group(1).replace(",", ".")), today(ctx).isoformat(), source="manual",
              note=m.group(2).strip()[:120])
    r.args = [str(pid)]
    return await person_card(ctx, r)


@screen("pa", "full")
async def adj_list(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    if len(r.args) > 1:
        a = K.adj(db, int(r.args[1]))
        from .panel_kassa import locked
        msg = locked(ctx, r, a["day"] if a else None)
        if msg:
            return msg
        if a is not None and a["kind"] == "adv" and not r.owner:
            return r.L("⛔ Avansni faqat ega o'zgartiradi", "⛔ Аванс меняет только владелец")
        K.adj_toggle(db, int(r.args[1]))
    p = must(P.person(db, pid))
    s, e = K.open_period(db, pid, today(ctx))
    items = K.person_adjs(db, pid, s - dt.timedelta(days=35), e)
    word = {"fine": r.L("jarima", "штраф"), "bonus": r.L("bonus", "бонус"), "adv": r.L("avans", "аванс")}
    rows = []
    for a in reversed(items[-20:]):
        mark = "✖️" if a["cancelled"] else "✅"
        rows.append([(f"{mark} {a['day'][8:10]}.{a['day'][5:7]} · {word.get(a['kind'], '?')} {money(a['usd'])} $ · "
                      f"{(a['note'] or a['source'])[:18]}", f"pa:{pid}:{a['id']}")])
    rows.append(nav(r, f"po:{pid}"))
    note = r.L("Bosing — bekor qilish / qaytarish. Joriy davr: ", "Нажмите — отменить / вернуть. Текущий период: ") + \
        plabel(s, e)
    return ui.join(title("📋", h(p["name"]), r.L("jarima · bonus · avans", "штрафы · бонусы · авансы")), "",
                   card([note])), kb(*rows)


# ───────────────────────── xodimga yuborish va oylik berildi
@screen("psd", "full")
async def send_preview(ctx, r: Req):
    db = ctx.db
    pid, key = int(r.args[0]), (r.args[1] if len(r.args) > 1 else "o")
    s, e, key = period_of(ctx, r, pid, key)
    p = must(P.person(db, pid))
    if not K.zp_state(db, s, e, today(ctx))["ready"]:
        return r.L("🧮 Avval haftani hisoblang (Kassa → 🧮 Haftani hisoblash)",
                   "🧮 Сначала рассчитайте неделю (Касса → 🧮 Рассчитать неделю)")
    row = K.calc(db, s, e)["rows"].get(pid)
    if row is None:
        return r.L("Ma'lumot yo'q", "Данных нет")
    msg = worker_message(row, s, e)
    if not p["tg_id"]:
        return r.L("⚠️ Xodim Telegram'ga ulanmagan: u botga /start bosishi kerak",
                   "⚠️ Сотрудник не подключён: пусть нажмёт /start у бота")
    text = ui.join(title("📤", h(p["name"]), r.L("xodim shuni ko'radi (hali yuborilmadi)",
                                                 "сотрудник увидит это (ещё не отправлено)")), "",
                   card([h(msg)]))
    return text, kb([(r.L("✅ Yuborish", "✅ Отправить"), f"psy:{pid}:{key}")], nav(r, f"po:{pid}:{key}"))


@screen("psy", "full")
async def send_do(ctx, r: Req):
    db = ctx.db
    pid, key = int(r.args[0]), r.args[1]
    s, e, key = period_of(ctx, r, pid, key)
    p = must(P.person(db, pid))
    if not K.zp_state(db, s, e, today(ctx))["ready"]:
        return r.L("🧮 Avval haftani hisoblang", "🧮 Сначала рассчитайте неделю")
    row = K.calc(db, s, e)["rows"].get(pid)
    if row is None or not p["tg_id"]:
        return r.L("⚠️ Yuborib bo'lmadi", "⚠️ Не отправлено")
    try:
        await ctx.bot.send_message(p["tg_id"], worker_message(row, s, e))
    except Exception:
        return r.L("⚠️ Yuborilmadi: xodim botni bloklagan yoki /start bosmagan",
                   "⚠️ Не отправлено: сотрудник заблокировал бота или не нажал /start")
    await ui.toast(ctx.bot, r.chat_id, r.L(f"✅ {h(p['name'])}ga yuborildi", f"✅ Отправлено: {h(p['name'])}"))
    r.args = [str(pid), key]
    return await person_card(ctx, r)


@screen("ppd", "owner")
async def paid_ask(ctx, r: Req):
    pid, key = int(r.args[0]), (r.args[1] if len(r.args) > 1 else "o")
    p = must(P.person(ctx.db, pid))
    s, e, key = period_of(ctx, r, pid, key)
    row = K.calc(ctx.db, s, e)["rows"].get(pid)
    total = row["total"] if row and K.zp_state(ctx.db, s, e, today(ctx))["ready"] else None
    lines = [r.L(f"Davr: <b>{plabel(s, e)}</b>", f"Период: <b>{plabel(s, e)}</b>")]
    if total is not None:
        lines.append(r.L(f"Jami: <b>{money(total)} $</b>", f"Итого: <b>{money(total)} $</b>"))
    lines.append(r.L("Shu kungacha hisob yopiladi — keyingi hisob noldan boshlanadi. Tarix saqlanadi.",
                     "Расчёт закрывается по эту дату — дальше считается с нуля. История сохранится."))
    return ui.join(title("✅", r.L("OYLIK BERILDI", "ЗП ВЫДАНА") + f" · {h(p['name'])}"), "", card(lines)), \
        kb([(r.L(f"✅ Ha, {e:%d.%m} gacha", f"✅ Да, по {e:%d.%m}"), f"ppy:{pid}:{e.isoformat()}")],
           nav(r, f"po:{pid}:{key}"))


@screen("ppy", "owner")
async def paid_do(ctx, r: Req):
    db = ctx.db
    pid, upto = int(r.args[0]), dt.date.fromisoformat(r.args[1])
    s, _e = K.open_period(db, pid, upto)
    row = K.calc(db, s, upto)["rows"].get(pid)
    ready = K.zp_state(db, s, upto, today(ctx))["ready"]
    K.mark_paid(db, pid, upto, row["total"] if row and ready else None)
    await ui.toast(ctx.bot, r.chat_id, r.L("✅ Belgilandi. Hisob noldan boshlandi.", "✅ Отмечено. Расчёт с нуля."))
    r.args = [str(pid)]
    return await person_card(ctx, r)


# ───────────────────────── sozlamalar
@screen("ps", "full")
async def person_settings(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = P.person(db, pid)
    if p is None or not visible(r, p):
        return await people_list(ctx, r)
    days = DAYS_RU if r.lang == "ru" else DAYS_UZ
    off = ", ".join(days[int(x)] for x in sorted(p["days_off"]) if x.isdigit()) or "—"
    lines = [f"✏️ {r.L('Ism', 'Имя')} — <b>{h(p['name'])}</b>",
             "✈️ Telegram — " + (f"@{h(p['username'])}" if p["username"] else "—") +
             (f" · 🆔 {p['tg_id']}" if p["tg_id"] else ""),
             f"🏷 {r.L('Turi', 'Тип')} — {kind_name(r, p['kassa_kind'])}"]
    if p["kassa_kind"] in ("worker", "self", "partner"):
        lines.append(f"💯 {r.L('Foiz', 'Процент')} — <b>{K.percent_on(db, pid, today(ctx)):g}%</b>")
    if p["kassa_kind"] in ("worker", "self"):
        lines.append(f"💰 {r.L('Zp hisoblash', 'Расчёт зп')} — {onoff(r, p['zp_on'])}")
    lines += [f"🙋 {r.L('Ishga kelish nazorati', 'Контроль прихода')} — {onoff(r, p['attend'])}",
              f"🛌 {r.L('Dam olish kunlari', 'Выходные')} — {off}"]
    rows = grid([(f"✏️ {r.L('Ism', 'Имя')}", f"pse:{pid}:name"), ("✈️ @username", f"pse:{pid}:user"),
                 (f"🏷 {r.L('Turi', 'Тип')}", f"psk:{pid}"),
                 (f"💯 {r.L('Foiz', 'Процент')}", f"pse:{pid}:pct") if p["kassa_kind"] in ("worker", "self", "partner")
                 else None,
                 ((r.L("💰 Zp: o'chirish", "💰 Зп: выкл") if p["zp_on"] else r.L("💰 Zp: yoqish", "💰 Зп: вкл")),
                  f"psz:{pid}") if p["kassa_kind"] in ("worker", "self") else None,
                 ((r.L("🙋 Nazorat: o'ch", "🙋 Контроль: выкл") if p["attend"] else r.L("🙋 Nazorat: yoq",
                                                                                         "🙋 Контроль: вкл")),
                  f"psa:{pid}"),
                 (f"🛌 {r.L('Dam olish', 'Выходные')}", f"psw:{pid}"), (f"📁 {r.L('Papkalar', 'Папки')}", f"psf:{pid}"),
                 (f"🔗 {r.L('Birlashtirish', 'Объединить')}", f"psm:{pid}"),
                 ((r.L("🗄 Arxivga", "🗄 В архив") if p["active"] else r.L("♻️ Qaytarish", "♻️ Вернуть")),
                  f"psr:{pid}"), (r.L("🗑 O'chirish", "🗑 Удалить"), f"psx:{pid}")])
    rows = [[b for b in row if b] for row in rows]
    rows.append(nav(r, f"po:{pid}"))
    return ui.join(title("⚙️", h(p["name"].upper())), "", card(lines)), kb(*rows)


@screen("psz", "full")
async def toggle_zp(ctx, r: Req):
    p = must(P.person(ctx.db, int(r.args[0])))
    P.update_person(ctx.db, p["id"], zp_on=0 if p["zp_on"] else 1)
    return await person_settings(ctx, r)


@screen("psa", "full")
async def toggle_attend(ctx, r: Req):
    p = must(P.person(ctx.db, int(r.args[0])))
    P.update_person(ctx.db, p["id"], attend=0 if p["attend"] else 1)
    return await person_settings(ctx, r)


@screen("psr", "full")
async def toggle_active(ctx, r: Req):
    p = must(P.person(ctx.db, int(r.args[0])))
    P.update_person(ctx.db, p["id"], active=0 if p["active"] else 1)
    return await person_settings(ctx, r)


@screen("psx", "full")
async def delete_person(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    use = P.person_usage(db, pid)
    money_data = use["checks"] or use["adj"] or use["worked"] or use["payouts"]
    if money_data and not r.owner:
        return r.L("⛔ Kassa yozuvlari bor — faqat ega o'chira oladi", "⛔ Есть записи кассы — удалить может только владелец")
    if len(r.args) > 1 and r.args[1] == "y":
        P.delete_person(db, pid)
        K.log(db, "person_del", None, None, pid, p["name"], "")
        ctx.tracker.reload()
        if ctx.userbot is not None:
            ctx.userbot.reload_ids()
        await ui.toast(ctx.bot, r.chat_id, r.L(f"🗑 {h(p['name'])} o'chirildi", f"🗑 {h(p['name'])} удалён"))
        r.args = []
        return await people_list(ctx, r)
    lines = [r.L(f"<b>{h(p['name'])}</b> butunlay o'chiriladi.", f"<b>{h(p['name'])}</b> будет удалён полностью.")]
    if money_data:
        lines.append(r.L(f"Birga o'chadi: {use['checks']} chek, {use['adj']} jarima/bonus/avans, {use['payouts']} to'lov "
                         "belgisi.", f"Вместе с ним: {use['checks']} чек., {use['adj']} штрафов/бонусов/авансов, "
                                    f"{use['payouts']} отметок выплаты."))
        if use["worked"]:
            lines.append(r.L(f"{use['worked']} ta chekda «ishlagan» sifatida turgan — u yerdan olib tashlanadi.",
                             f"В {use['worked']} чеках указан как «работал» — будет снят."))
    lines.append(r.L("Faqat vaqtincha kerak bo'lmasa — «🗄 Arxivga» yaxshiroq: tarix saqlanadi.",
                     "Если временно — лучше «🗄 В архив»: история сохранится."))
    return ui.join(title("🗑", r.L("XODIMNI O'CHIRISH", "УДАЛИТЬ СОТРУДНИКА")), "", card(lines)), \
        kb([(r.L("🗑 Ha, o'chirish", "🗑 Да, удалить"), f"psx:{pid}:y")], [(r.L("✖️ Yo'q", "✖️ Нет"), ui.back_data(f"ps:{pid}"))])


@screen("psw", "full")
async def days_off(ctx, r: Req):
    pid = int(r.args[0])
    p = must(P.person(ctx.db, pid))
    if len(r.args) > 1:
        d = r.args[1]
        cur = set(p["days_off"] or "")
        cur ^= {d}
        P.update_person(ctx.db, pid, days_off="".join(sorted(cur)))
        p = must(P.person(ctx.db, pid))
    days = DAYS_RU if r.lang == "ru" else DAYS_UZ
    btn = [((("🛌 " if str(i) in (p["days_off"] or "") else "▫️ ") + days[i]), f"psw:{pid}:{i}") for i in range(7)]
    return ui.join(title("🛌", h(p["name"]), r.L("dam olish kunlari", "выходные дни")), "",
                   card([r.L("Bu kunlarda kech qolish tekshirilmaydi, zaderjka jarimasi yozilmaydi.",
                             "В эти дни опоздания не проверяются, штрафы за задержки не начисляются.")])), \
        kb(*grid(btn, 4), nav(r, f"ps:{pid}"))


@screen("psf", "full")
async def person_folders(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    if len(r.args) > 1:
        P.toggle_folder_person(db, int(r.args[1]), pid)
    mine = {f["id"] for f in P.person_folders(db, pid)}
    btn = [((("✅ " if f["id"] in mine else "▫️ ") + f["name"]), f"psf:{pid}:{f['id']}") for f in P.folders(db)]
    p = must(P.person(db, pid))
    return ui.join(title("📁", h(p["name"]), r.L("qaysi papkalarda ishlaydi", "в каких папках работает")), "",
                   card([r.L("Papkadagi zaderjkada belgilanadi va jarima oladi.",
                             "Отмечается в задержках папки и получает штраф.")])), \
        kb(*grid(btn), nav(r, f"ps:{pid}"))


@screen("psk", "full")
async def person_kind(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    if len(r.args) > 1:
        kind = r.args[1] if r.args[1] != "none" else ""
        if kind == "self" and not r.owner:
            return r.L("⛔ Faqat ega", "⛔ Только владелец")
        if kind and not db.one("SELECT 1 FROM pct WHERE person_id=?", (pid,)):
            K.set_percent(db, pid, 50 if kind in ("self", "partner") else 30, "2000-01-01")
        P.update_person(db, pid, kassa_kind=kind)
        return await person_settings(ctx, r)
    opts = [("none", r.L("👤 Faqat nazorat (kassasiz)", "👤 Только контроль (без кассы)")),
            ("worker", r.L("💼 Kassa xodimi (foiz bilan)", "💼 Обработчик (с процентом)")),
            ("pool", r.L("🔁 Umumiy akkaunt", "🔁 Общий аккаунт"))]
    if r.owner:
        opts += [("partner", r.L("🤝 Hamkor (kassadan %)", "🤝 Партнёр (% от кассы)")),
                 ("self", r.L("👑 Ega (siz)", "👑 Владелец (вы)"))]
    cur = p["kassa_kind"] or "none"
    rows = [[(("● " if k == cur else "○ ") + t, f"psk:{pid}:{k}")] for k, t in opts]
    rows.append(nav(r, f"ps:{pid}"))
    return title("🏷", h(p["name"]), r.L("turi", "тип")), kb(*rows)


@screen("pse", "full")
async def edit_ask(ctx, r: Req):
    pid, field = int(r.args[0]), r.args[1]
    if field == "pct" and not r.owner:
        return r.L("⛔ Foizni faqat ega o'zgartiradi", "⛔ Процент меняет только владелец")
    ui.ask(r, "person_edit", f"ps:{pid}", pid=pid, field=field)
    prompts = {"name": r.L("Yangi ismni yuboring.", "Пришлите новое имя."),
               "user": r.L("@username yuboring (yoki <code>-</code> — olib tashlash).",
                           "Пришлите @username (или <code>-</code> — убрать)."),
               "pct": r.L("Yangi foizni yuboring, masalan <code>41</code>.", "Пришлите новый процент, например "
                                                                              "<code>41</code>.")}
    return title("✏️", r.L("O'ZGARTIRISH", "ИЗМЕНИТЬ")) + "\n\n" + card([prompts[field]]), ui.cancel_kb(r, f"ps:{pid}")


@on_input("person_edit")
async def edit_do(ctx, r: Req, pid: int, field: str):
    db = ctx.db
    text = r.text.strip()
    if field == "name":
        if not text or len(text) > 40:
            return r.L("⚠️ Ism 1–40 belgi", "⚠️ Имя 1–40 символов")
        P.update_person(db, pid, name=text)
    elif field == "user":
        u = "" if text in ("-", "—") else P.norm_username(text)
        if u and not P.valid_username(u):
            return r.L("⚠️ @username noto'g'ri", "⚠️ Неверный @username")
        other = P.by_username(db, u) if u else None
        if other is not None and other["id"] != pid:
            return r.L("⚠️ Bu @username boshqa xodimda", "⚠️ Этот @username у другого сотрудника")
        P.update_person(db, pid, username=u)
        if ctx.userbot is not None and ctx.userbot.state == "online":
            ui.bg(ctx.userbot.resolve_people())
    elif field == "pct":
        v = parse_number(text)
        if v is None or not 0 <= v <= 100:
            return r.L("⚠️ 0 dan 100 gacha son", "⚠️ Число от 0 до 100")
        t = today(ctx)
        mon = K.week_start(t)
        return (title("💯", f"{v:g}%", r.L("qaysi kundan?", "с какого дня?")) + "\n\n" +
                card([r.L("O'tgan kunlar eski foizda qoladi.", "Прошлые дни останутся по старому проценту.")]),
                kb([(r.L("Shu hafta dushanbasidan", "С понедельника этой недели"), f"psp:{pid}:{v:g}:{mon}")],
                   [(r.L("Bugundan", "С сегодня"), f"psp:{pid}:{v:g}:{t}"),
                    (r.L("Ertadan", "С завтра"), f"psp:{pid}:{v:g}:{t + dt.timedelta(days=1)}")],
                   [(r.L("Hamma vaqt uchun", "За всё время"), f"psp:{pid}:{v:g}:2000-01-01")], nav(r, f"ps:{pid}")))
    r.args = [str(pid)]
    return await person_settings(ctx, r)


@screen("psp", "owner")
async def pct_set(ctx, r: Req):
    pid, v, day = int(r.args[0]), float(r.args[1]), r.args[2]
    if day == "2000-01-01":
        ctx.db.run("DELETE FROM pct WHERE person_id=?", (pid,))
    K.set_percent(ctx.db, pid, v, day)
    r.args = [str(pid)]
    return await person_settings(ctx, r)


@screen("psm", "full")
async def merge_pick(ctx, r: Req):
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    if len(r.args) > 1:
        other = int(r.args[1])
        o = must(P.person(db, other))
        return ui.join(title("🔗", r.L("BIRLASHTIRISH", "ОБЪЕДИНИТЬ")), "", card(
            [r.L(f"<b>{h(o['name'])}</b> yozuvi <b>{h(p['name'])}</b> ga qo'shiladi (kassa, jarima, papkalar, "
                 f"Telegram). Keyin «{h(o['name'])}» o'chadi.",
                 f"Запись <b>{h(o['name'])}</b> войдёт в <b>{h(p['name'])}</b> (касса, штрафы, папки, Telegram). "
                 f"Потом «{h(o['name'])}» удалится.")])), \
            kb([(r.L("✅ Birlashtirish", "✅ Объединить"), f"psmy:{pid}:{other}")], nav(r, f"ps:{pid}"))
    btn = [(f"{KIND_ICON.get(o['kassa_kind'], '👤')} {o['name']}", f"psm:{pid}:{o['id']}")
           for o in P.people(db, active_only=False) if o["id"] != pid and visible(r, o)]
    return ui.join(title("🔗", h(p["name"]), r.L("bitta odamning ikkinchi yozuvi qaysi?",
                                                "какая запись — тот же человек?")), "",
                   card([r.L("Masalan kassadagi «Bayzed» va nazoratdagi «@bayzed» — bitta odam.",
                             "Например «Bayzed» из кассы и «@bayzed» из контроля — один человек.")])), \
        kb(*grid(btn), nav(r, f"ps:{pid}"))


@screen("psmy", "full")
async def merge_do(ctx, r: Req):
    keep, drop = int(r.args[0]), int(r.args[1])
    P.merge_people(ctx.db, keep, drop)
    r.args = [str(keep)]
    return await person_settings(ctx, r)
