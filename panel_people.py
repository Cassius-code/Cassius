"""👥 Xodimlar: ro'yxat, kabinet (kassa + zp + jarima/bonus), sozlamalar, oylik berildi, xodimga yuborish."""
from __future__ import annotations

import datetime as dt
import re

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
    return {"self": r.L("ega (siz)", "владелец (вы)") if r.owner else r.L("ega", "владелец"),
            "partner": r.L("hamkor", "партнёр"),
            "pool": r.L("umumiy akkaunt", "общий аккаунт"), "worker": r.L("kassa xodimi", "обработчик"),
            "": r.L("faqat nazorat", "только контроль")}[kind]


def visible(r: Req, p) -> bool:
    """Egasi va Artur (hamkor) — adminlarga ko'rinmaydi; Artur o'zi (r.partner) — egasini (xodim sifatida) va o'zini
    ko'radi."""
    return r.owner or r.partner or p["kassa_kind"] not in ("self", "partner")


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
    if r.owner and not archived:                       # 🤝 Artur — botga ulash: alohida tugma (egasi, 2026-11-12)
        pr = partner_rec(db)
        rows.append([(f"🤝 {pr['name']} · ✅ {r.L('botda', 'в боте')}" if pr is not None and pr["tg_id"] else
                      f"🤝 {pr['name'] if pr is not None else 'Artur'} — {r.L('botga ulash', 'подключить к боту')}",
                      "pal")])
    tw = P.twins(db) if not archived and r.can("full") else []
    if tw:
        rows.insert(0, [(r.L(f"🔗 Bitta odamning 2 yozuvi: {len(tw)}", f"🔗 Две записи одного человека: {len(tw)}"),
                         "ptw")])
    if not archived:
        rows.append([(r.L("📅 Bugun kim qayerda", "📅 Кто где сегодня"), "rt"),
                     (r.L("🏆 Haftalik ball", "🏆 Баллы недели"), "psc")])
    if r.can("full") and not archived:
        rows.append([(r.L("➕ Yangi xodim", "➕ Новый сотрудник"), "pn"), (r.L("🗄 Arxiv", "🗄 Архив"), "p:a")])
    rows.append(nav(r, "p" if archived else "m"))
    legend = r.L("👑 ega · 💼 kassa xodimi · 🔁 umumiy akkaunt · 🤝 hamkor · 👤 faqat nazorat",
                 "👑 владелец · 💼 обработчик · 🔁 общий аккаунт · 🤝 партнёр · 👤 только контроль")
    head = title("👥", r.L("XODIMLAR", "СОТРУДНИКИ") + (r.L(" · ARXIV", " · АРХИВ") if archived else ""))
    body = card([legend]) if ps else r.L("<i>Hozircha hech kim yo'q.</i>", "<i>Пока никого нет.</i>")
    return ui.join(head, "", body), kb(*rows)


# ───────────────────────── 🤝 Artur — botga ulash (alohida tugma; egasi, 2026-11-12)
def partner_rec(db):
    return db.one("SELECT * FROM people WHERE kassa_kind='partner' AND active=1 ORDER BY id LIMIT 1")


def _partner_about(r: Req) -> str:
    return r.L("Artur botda faqat ko'radi: kassa, hamma zp (foizlari bilan), kunma-kun, zaderjka doskasi, lidlar. Hech "
               "narsani o'zgartira olmaydi. Xodimlarning kunlik xulosalari va kunlik 📊 hisobot unga ham boradi.",
               "Артур в боте только смотрит: касса, все зп (с процентами), по дням, доска задержек, лиды. Ничего не "
               "меняет. Дневные сводки сотрудников и дневной 📊 отчёт приходят и ему.")


@screen("pal", "owner")
async def partner_link(ctx, r: Req):
    """🤝 Artur botga: @username yoziladi → Artur /start bossa, bot uni o'zi taniydi (faqat ko'radi). Hamkor yozuvi
    hali yo'q bo'lsa — shu yerda qo'shiladi (ism + @username)."""
    db = ctx.db
    p = partner_rec(db)
    if p is None:
        ui.ask(r, "pal_new", "p")
        return ui.join(title("🤝", r.L("ARTUR QO'SHISH", "ДОБАВИТЬ АРТУРА")), "", card([
            r.L("Ismi va @username ini yozing, masalan: <code>Artur @artur</code>",
                "Напишите имя и @username, например: <code>Artur @artur</code>"), _partner_about(r)])), \
            ui.cancel_kb(r, "p")
    if (not p["username"] and not p["tg_id"]) or (r.args and r.args[0] == "e"):
        ui.ask(r, "pal_user", "pal", pid=p["id"])
        return ui.join(title("🤝", h(p["name"]), r.L("botga ulash", "подключить к боту")), "", card([
            r.L(f"{h(p['name'])}ning @username ini yozing, masalan <code>@artur</code>. Keyin u botga /start bossin.",
                f"Напишите @username {h(p['name'])}, например <code>@artur</code>. Потом пусть нажмёт /start у бота."),
            _partner_about(r)])), ui.cancel_kb(r, "pal" if (p["username"] or p["tg_id"]) else "p")
    head = r.L("botda", "в боте") if p["tg_id"] else r.L("botga ulash", "подключить к боту")
    return ui.join(title("🤝", h(p["name"]), head), "", card([tg_line(r, p) or "", _partner_about(r)])), \
        kb([(r.L("✏️ @username o'zgartirish", "✏️ Изменить @username"), "pal:e")],
           [(f"🤝 {p['name']} — {r.L('kabinet', 'кабинет')}", f"po:{p['id']}")], nav(r, "p"))


@on_input("pal_user", "owner")
async def partner_user(ctx, r: Req, pid: int):
    db = ctx.db
    u = P.norm_username((r.text or "").strip())
    if not u or not P.valid_username(u):
        return r.L("⚠️ @username noto'g'ri — masalan @artur", "⚠️ Неверный @username — например @artur")
    other = P.by_username(db, u)
    if other is not None and other["id"] != pid:        # Artur nazoratda alohida yozuv bo'lib turgan bo'lsa
        ui.WAIT.pop(r.uid, None)
        me = must(P.person(db, pid))
        return ui.join(title("🔗", r.L("BU @USERNAME BOSHQA YOZUVDA", "ЭТОТ @USERNAME В ДРУГОЙ ЗАПИСИ")), "", card(
            [r.L(f"@{h(u)} — «{h(other['name'])}» yozuvida. Bitta odam bo'lsa — birlashtiring: «{h(other['name'])}» "
                 f"«{h(me['name'])}»ga qo'shiladi.",
                 f"@{h(u)} — в записи «{h(other['name'])}». Если это один человек — объедините: «{h(other['name'])}» "
                 f"войдёт в «{h(me['name'])}».")])), \
            kb([(r.L("🔗 Birlashtirish", "🔗 Объединить"), f"psmy:{pid}:{other['id']}")], nav(r, "pal"))
    P.update_person(db, pid, username=u)
    if ctx.userbot is not None and getattr(ctx.userbot, "state", "") == "online":
        ui.bg(ctx.userbot.resolve_people())
    ui.WAIT.pop(r.uid, None)
    await ui.toast(ctx.bot, r.chat_id, f"✅ @{u}")
    r.args = []
    return await partner_link(ctx, r)


@on_input("pal_new", "owner")
async def partner_new(ctx, r: Req):
    db = ctx.db
    text = (r.text or "").strip()
    m = re.search(r"@([A-Za-z][A-Za-z0-9_]{3,31})", text)
    name = re.sub(r"@\S+", "", text).strip() or "Artur"
    if m is None or not P.valid_username(P.norm_username(m.group(1))):
        return r.L("⚠️ Ism va @username yozing, masalan: Artur @artur", "⚠️ Имя и @username, например: Artur @artur")
    u = P.norm_username(m.group(1))
    other = P.by_username(db, u)
    if other is not None:                              # shu @username bilan yozuv bor — o'sha hamkor bo'ladi
        P.update_person(db, other["id"], kassa_kind="partner")
        pid = other["id"]
    else:
        pid = P.add_person(db, name[:40], u, None, "partner")
    if not db.one("SELECT 1 FROM pct WHERE person_id=?", (pid,)):
        K.set_percent(db, pid, 50, "2000-01-01")
    ui.WAIT.pop(r.uid, None)
    r.args = []
    return await partner_link(ctx, r)


@screen("ptw", "full")
async def twins_list(ctx, r: Req):
    """🔗 Kassadagi «Baxa» va nazoratdagi «@baxa» — bitta odam bo'lsa birlashtiriladi (bot uni hamma joyda taniydi)."""
    lines, rows = [], []
    for k, c in P.twins(ctx.db):
        who = f"@{c['username']}" if c["username"] else c["name"]
        lines.append(f"💼 {h(k['name'])}  ↔  👤 {h(who)}")
        rows.append([(f"🔗 {k['name']} + {who}"[:40], f"psmy:{k['id']}:{c['id']}")])
    note = r.L("Kassadagi va nazoratdagi yozuv bir xil ismli. Bitta odam bo'lsa — bosing: hisobotlari, jarimalari, "
               "ishga kelishi va RD lari bitta yozuvda bo'ladi. Boshqa-boshqa odam bo'lsa — tegmang.",
               "Записи в кассе и в контроле с одинаковым именем. Если это один человек — нажмите: отчёты, штрафы, приход "
               "и RD будут в одной записи. Если разные люди — не трогайте.")
    rows.append(nav(r, "p"))
    body = card(lines) if lines else r.L("<i>Hammasi joyida 👍</i>", "<i>Всё в порядке 👍</i>")
    return ui.join(title("🔗", r.L("BIRLASHTIRISH", "ОБЪЕДИНИТЬ")), "", body, f"<i>{note}</i>"), kb(*rows)


async def offer_twins(ctx) -> int:
    """Yangi topilgan «bitta odamning 2 yozuvi» — egasiga bir marta so'rov (tugma bilan)."""
    from .panel_kassa import ask_merge
    n = 0
    for k, c in P.twins(ctx.db):
        if not ctx.db.get(f"twin_asked:{k['id']}:{c['id']}"):
            await ask_merge(ctx, k, c)
            n += 1
    return n


# ───────────────────────── 🏆 haftalik ball
@screen("psc", "view")
async def scores(ctx, r: Req):
    """🏆 Haftalik ball: har xodim 0–100 (⚡ tezlik · 🚨 zaderjka · 💳 karta · 🕘 intizom), 🔥 seriya, maslahat."""
    from . import score as S
    last = bool(r.args and r.args[0] == "lw")
    day = today(ctx) - dt.timedelta(days=7 if last else 0)
    s, e, _a, _b = S.week_bounds(day, ctx.tz)
    rows = S.compute(ctx, s, e)
    medals = ["🥇", "🥈", "🥉"]
    lines, place = [], 0
    for x in rows:
        name = h(x["p"]["name"])
        if x["score"] is None:
            lines.append(f"▫️ {name} — {r.L('ma‘lumot kam', 'мало данных')} ({x['n']} {r.L('javob', 'отв.')})")
            continue
        mark = medals[place] if place < 3 else f"{place + 1}."
        place += 1
        fire = f" · 🔥{x['streak']}" if x["streak"] >= 3 else ""
        lines.append(f"{mark} <b>{name} — {x['score']}</b> · {S.parts_line(x)}{fire}")
        lines.append(f"<i>{h(S.advice(x, r.lang))}</i>")
    if not lines:
        lines = [r.L("Hozircha ma'lumot yo'q.", "Пока нет данных.")]
    head = title("🏆", r.L("HAFTALIK BALL", "БАЛЛЫ НЕДЕЛИ"),
                 f"{plabel(s, e)} · " + (r.L("o'tgan hafta", "прошлая неделя") if last else r.L("shu hafta", "эта неделя")))
    legend = r.L("⚡ tezlik · 🚨 zaderjka · 💳 karta · 🕘 intizom — har biri 25 ball. 🔥 — ketma-ket zaderjkasiz "
                 "ish kunlari. Pulga bog'lanmagan.",
                 "⚡ скорость · 🚨 задержки · 💳 карты · 🕘 дисциплина — по 25 баллов. 🔥 — рабочие дни подряд без "
                 "задержек. С деньгами не связано.")
    rows_kb = [[(r.L("🗓 Shu hafta", "🗓 Эта неделя"), "psc") if last else
                (r.L("🗓 O'tgan hafta", "🗓 Прошлая неделя"), "psc:lw"),
                (r.L("ℹ️ Qanday hisoblanadi", "ℹ️ Как считается"), "psci")]]
    rows_kb.append(nav(r, "p"))
    return ui.join(head, "", card(lines), f"<i>{legend}</i>"), kb(*rows_kb)


@screen("psci", "view")
async def scores_info(ctx, r: Req):
    lim = ctx.db.get_int("limit_minutes", 20)
    lines = [r.L("<b>⚡ Tezlik (25)</b> — o'rtacha javob vaqti: 3 daqiqagacha — 25, "
                 f"{lim} daqiqa va ko'p — 0.",
                 "<b>⚡ Скорость (25)</b> — среднее время ответа: до 3 мин — 25, "
                 f"{lim} мин и больше — 0."),
             r.L("<b>🚨 Zaderjka (25)</b> — har 100 javobga nechta «задержка» (o'sha kuni papkada ishlagan bo'lsa): "
                 "0 — 25, 10 va ko'p — 0.",
                 "<b>🚨 Задержки (25)</b> — сколько «задержек» на 100 ответов (если в тот день работал в папке): "
                 "0 — 25, 10 и больше — 0."),
             r.L("<b>💳 Karta (25)</b> — javob bergan lidlaridan nechtasiga karta ketdi, jamoa o'rtachasiga "
                 "nisbatan: 1.5 barobar va ko'p — 25.",
                 "<b>💳 Карты (25)</b> — какой доле его лидов ушла карта, по сравнению со средним по команде: "
                 "в 1.5 раза выше и больше — 25."),
             r.L("<b>🕘 Intizom (25)</b> — 25 dan ayriladi: har 5 daqiqa kechikish — 1, eslatmadan keyin ham "
                 "javob bermaslik — 5.",
                 "<b>🕘 Дисциплина (25)</b> — из 25 вычитается: каждые 5 мин опоздания — 1, нет ответа после "
                 "напоминания — 5."),
             r.L("Haftada 20 tadan kam javob bo'lsa — ball qo'yilmaydi.", "Меньше 20 ответов за неделю — без балла."),
             r.L("Ball pulga bog'lanmagan. Xodim o'z balini haftalik zp xabarida ko'radi, «Проёб»da — /statistika.",
                 "Балл не связан с деньгами. Сотрудник видит свой балл в недельном сообщении о зп, в «Проёб» — "
                 "/statistika.")]
    return ui.join(title("ℹ️", r.L("BALL QANDAY HISOBLANADI", "КАК СЧИТАЕТСЯ БАЛЛ")), "", card(lines)), \
        kb(nav(r, "psc"))


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
def tg_line(r: Req, p) -> str | None:
    """Bot bu xodimni Telegram'da taniydimi: ✅ — ID bog'langan; ⏳ — hali yozmagan (yozsa — o'zi taniydi)."""
    if p["kassa_kind"] == "partner":                     # 🤝 Artur — @username bilan botda faqat ko'rish (2026-11-12)
        user = f"@{h(p['username'])}" if p["username"] else ""
        if p["tg_id"]:
            return f"✈️ {user} · ✅ " + r.L("botda: kassa, zp (foizlari bilan), lidlar, doska — faqat ko'radi",
                                           "в боте: касса, зп (с процентами), лиды, доска — только просмотр")
        if p["username"]:
            return f"✈️ {user} · ⏳ " + r.L("botga /start bossin — kassa, zp, lidlar va doskani ko'radi",
                                           "пусть нажмёт /start у бота — увидит кассу, зп, лидов и доску")
        return "✈️ " + r.L("⚙️ Sozlamalar → ✈️ @username yozing — Artur botda kassa, zp va doskani ko'radi",
                           "⚙️ Настройки → ✈️ укажите @username — Артур увидит в боте кассу, зп и доску")
    if p["kassa_kind"] in ("self", "pool"):
        return f"✈️ @{h(p['username'])}" if p["username"] else None
    user = f"@{h(p['username'])}" if p["username"] else r.L("@username yo'q", "нет @username")
    if p["tg_id"]:
        return f"✈️ {user} · ✅ {r.L('bot taniydi', 'бот узнаёт')}"
    if p["username"]:
        return f"✈️ {user} · ⏳ " + r.L("hali yozmagan — «Проёб»ga yoki lidga yozsa, o'zi taniydi",
                                       "ещё не писал — напишет в «Проёб» или лиду, бот узнает сам")
    return f"✈️ {user} · ⚠️ " + r.L("⚙️ Sozlamalar → ✈️ @username yozing", "⚙️ Настройки → ✈️ укажите @username")


def period_of(ctx, r: Req, pid: int, key: str | None):
    t = today(ctx)
    if not key:                                          # kabinet — hafta boshidan (egasi, 2026-11-12: «nega 02 dan
        key = "tw"                                       # 12 gacha? hafta boshidan emas?»); oxirgi oylikdan — 📅 Davr
    if key == "o":
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
            tg_line(r, p)]
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
            if p["kassa_kind"] in ("worker", "self") and p["zp_on"] and \
                    not db.one("SELECT 1 FROM pct WHERE person_id=? AND percent>0", (pid,)):
                parts.append(card([r.L("⚠️ Foiz yozilmagan — zp 0 chiqadi. ⚙️ Sozlamalar → 💯 Foiz.",
                                       "⚠️ Процент не задан — зп будет 0. ⚙️ Настройки → 💯 Процент.")]))
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
    if r.can("full") and (r.owner or p["kassa_kind"] not in ("self", "partner")):   # ega/Artur kartasi — faqat ko'rish
        if p["kassa_kind"] != "pool":                     # ochiq turgan davr bilan — kun shu davrdan tanlanadi
            rows += [[(r.L("⚠️ Jarima", "⚠️ Штраф"), f"paf:{pid}:{key}"),
                      (r.L("🎁 Bonus", "🎁 Бонус"), f"pab:{pid}:{key}"),
                      (r.L("💸 Avans", "💸 Аванс"), f"paa:{pid}:{key}") if r.owner else None]]
        rows += grid([(r.L("📋 Jarima/bonuslar", "📋 Штрафы/бонусы"), f"pa:{pid}"), (r.L("📅 Davr", "📅 Период"),
                                                                                      f"pp:{pid}")])
        if p["kassa_kind"] in ("worker", "self", "pool") and (p["kassa_kind"] != "self" or r.owner):
            rows.append([(r.L("📄 PDF (shu davr)", "📄 PDF (за период)"), f"ppf:{pid}:{key}")])
        if p["kassa_kind"] in ("worker", "self", "pool"):
            rows += grid([(r.L("🧾 Cheklar", "🧾 Чеки"), f"kx:{pid}:{key}"), (r.L("🔁 Kim ishladi", "🔁 Кто работал"),
                                                                               f"kw:{pid}")])
        if p["kassa_kind"] in ("worker", "partner"):
            rows += grid([(r.L("🔀 Zp o'tkazish", "🔀 Перенос зп"), f"kt:{pid}")]
                         + ([(r.L("🤝 Ulushlar", "🤝 Доли"), f"ksh:{pid}")] if r.owner else []))
        if p["kassa_kind"] == "worker":
            rows += grid([(r.L("📤 Xodimga yuborish", "📤 Отправить ему"), f"psd:{pid}:{key}")]
                         + ([(r.L("✅ Oylik berildi", "✅ Зп выдана"), f"ppd:{pid}:{key}")] if r.owner else []))
        if r.owner and p["kassa_kind"] == "worker":      # egasi o'zini xodimlar orasida belgilaydi (2026-11-02)
            rows.append([(r.L("👑 Bu menman", "👑 Это я"), f"pme:{pid}")])
        rows.append([(r.L("⚙️ Sozlamalar", "⚙️ Настройки"), f"ps:{pid}")])
    else:
        rows.append([(r.L("📅 Davr", "📅 Период"), f"pp:{pid}")])
    rows.append(nav(r, "p"))
    return ui.join(*parts), kb(*rows)


@screen("pme", "owner")
async def person_is_me(ctx, r: Req):
    """👑 Bu menman: shu xodim — ega (siz). Uning kassasidan foizingiz va boshqa xodimlardan ulushingiz «👑 Siz»
    kartasida birga hisoblanadi; uning zp si «Xodimlar zp si»ga qo'shilmaydi. Oldin boshqasi «siz» bo'lsa — xodim."""
    db = ctx.db
    pid = int(r.args[0])
    p = must(P.person(db, pid))
    old = db.one("SELECT id, name FROM people WHERE kassa_kind='self' AND id<>?", (pid,))
    if len(r.args) > 1 and r.args[1] == "y":
        if old is not None:
            P.update_person(db, old["id"], kassa_kind="worker")
        P.update_person(db, pid, kassa_kind="self")
        r.args = ui.last_args(r, "po", str(pid)) or [str(pid)]
        return await person_card(ctx, r)
    nm = h(p["name"])
    lines = [r.L(f"Bot <b>{nm}</b> ni siz deb biladi:", f"Бот будет знать, что <b>{nm}</b> — это вы:"),
             r.L(f"• {nm} kassasidan foizingiz va boshqa xodimlardan ulushingiz «👑 Siz» kartasida birga "
                 f"hisoblanadi;", f"• ваш процент с кассы {nm} и ваша доля с других сотрудников считаются вместе "
                 f"в карточке «👑 Вы»;"),
             r.L(f"• {nm} zp si «Xodimlar zp si»ga qo'shilmaydi (o'zingizga o'zingiz to'lamaysiz);",
                 f"• зп {nm} не входит в «Зарплаты сотрудников» (себе вы не платите);"),
             r.L("• «Проёб»ga ismsiz yozgan hisobotingiz — sizniki bo'ladi.",
                 "• ваш отчёт в «Проёб» без имени — будет вашим.")]
    if old is not None:
        lines.append(r.L(f"Oldin «{h(old['name'])}» siz deb belgilangan edi — u oddiy xodim bo'ladi.",
                         f"Раньше вами был отмечен «{h(old['name'])}» — он станет обычным сотрудником."))
    lines.append(r.L("Qaytarish: ⚙️ Sozlamalar → 🏷 Turi.", "Вернуть: ⚙️ Настройки → 🏷 Тип."))
    return ui.join(title("👑", nm, r.L("bu menman", "это я")), "", card(lines)), \
        kb([(r.L("✅ Ha, bu menman", "✅ Да, это я"), f"pme:{pid}:y")], nav(r, f"po:{pid}"))



@screen("ppf", "full")
async def person_pdf(ctx, r: Req):
    """📄 Xodimning shu davrdagi kassasi, cheklari (kun bo'yicha), bonus/jarima va zp si — PDF."""
    import asyncio
    db = ctx.db
    pid, key = int(r.args[0]), (r.args[1] if len(r.args) > 1 else "o")
    p = must(P.person(db, pid))
    if not visible(r, p):
        return r.L("⛔ Bu xodim faqat egaga ko'rinadi", "⛔ Только владельцу")
    s, e, key = period_of(ctx, r, pid, key)
    b = K.calc(db, s, e)
    row = b["rows"].get(pid)
    if row is None:
        return r.L("Ma'lumot yo'q", "Данных нет")
    ready = K.zp_state(db, s, e, today(ctx))["ready"]
    from . import pdfgen
    ui.effect()
    try:
        data = await asyncio.to_thread(pdfgen.person_pdf, b, row, s, e, r.lang, r.owner, ready)
    except Exception as exc:
        return r.L(f"⚠️ PDF yaratilmadi: {h(exc)}", f"⚠️ PDF не создан: {h(exc)}")
    safe = "".join(ch for ch in p["name"] if ch.isalnum())[:20] or "xodim"
    await ctx.notifier.send_document(r.chat_id, data, f"{safe}_{s.isoformat()}_{e.isoformat()}.pdf",
                                     f"📄 {p['name']} · {plabel(s, e)}")
    r.args = [str(pid), key]
    return await person_card(ctx, r)


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
    """Summa so'raladi; kun — tugma bilan (egasi, 2026-11-02: «qaysi kun uchun» so'rasin). Kabinetda o'tgan davr
    ochiq bo'lsa — o'sha davr kunlari (oxirgi 7 tasi), joriy davrda — oxirgi 7 kun; oldindan — davrning oxirgi kuni."""
    pid = int(r.args[0])
    p = must(P.person(ctx.db, pid))
    t = today(ctx)
    s, e, key = period_of(ctx, r, pid, r.args[1] if len(r.args) > 1 else None)
    last = min(e, t)
    days = [d for d in (last - dt.timedelta(days=i) for i in range(6, -1, -1)) if d >= s or e >= t] or [t]
    day = dt.date.fromisoformat(r.args[2]) if len(r.args) > 2 else days[-1]
    ui.ask(r, "adj_add", f"po:{pid}:{key}", pid=pid, kind=kind, day=day.isoformat(), key=key)
    word = {"fine": r.L("JARIMA", "ШТРАФ"), "bonus": r.L("BONUS", "БОНУС"), "adv": r.L("AVANS", "АВАНС")}[kind]
    cmd = {"fine": "paf", "bonus": "pab", "adv": "paa"}[kind]
    wd = DAYS_RU if r.lang == "ru" else DAYS_UZ
    btn = [((("● " if d == day else "") + f"{wd[d.weekday()]} {d:%d.%m}"), f"{cmd}:{pid}:{key}:{d.isoformat()}")
           for d in days]
    when = r.L(" (bugun)", " (сегодня)") if day == t else (r.L(" (kecha)", " (вчера)") if day == t - dt.timedelta(days=1)
                                                          else "")
    lines = [r.L(f"📅 Qaysi kun uchun: <b>{day:%d.%m}</b>{when} — boshqa kun bo'lsa, pastdan tanlang.",
                 f"📅 За какой день: <b>{day:%d.%m}</b>{when} — если за другой, выберите ниже."),
             r.L("Summani $ da yuboring, xohlasangiz izoh bilan: <code>5 kech qoldi</code>.",
                 "Пришлите сумму в $, можно с пояснением: <code>5 опоздал</code>.")]
    sub = K.stand_in(ctx.db, pid, day) if kind != "adv" else None
    if sub:                                             # shu kuni uning o'rniga boshqasi ishlagan — o'shanga o'tadi
        sn = h(P.person(ctx.db, sub)["name"])
        lines.append(r.L(f"↪ Bu kuni {h(p['name'])} o'rniga <b>{sn}</b> ishlagan («🔁 Kim ishladi») — {sn}ga "
                         f"hisoblanadi.", f"↪ В этот день вместо {h(p['name'])} работал(а) <b>{sn}</b> («🔁 Кто "
                         f"работал») — пойдёт {sn}."))
    return title({"fine": "⚠️", "bonus": "🎁", "adv": "💸"}[kind], f"{word} · {h(p['name'])}") + "\n\n" + \
        card(lines), kb(*grid(btn, 4), [(r.L("✖️ Bekor qilish", "✖️ Отмена"), ui.back_data(f"po:{pid}:{key}"))])


@on_input("adj_add")
async def adj_add(ctx, r: Req, pid: int, kind: str, day: str | None = None, key: str = "o"):
    import re
    from .panel_kassa import locked
    day = day or today(ctx).isoformat()                 # eski so'rov (yangilanishdan oldin) — bugun
    if kind == "adv" and not r.owner:
        ui.WAIT.pop(r.uid, None)
        return r.L("⛔ Avansni faqat ega yozadi", "⛔ Аванс записывает только владелец")
    msg = locked(ctx, r, day)
    if msg:
        ui.WAIT.pop(r.uid, None)
        return msg
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*\$?\s*(.*)$", r.text, re.S)
    if not m or float(m.group(1).replace(",", ".")) <= 0:
        return r.L("⚠️ Summa kerak, masalan 5", "⚠️ Нужна сумма, например 5")
    K.add_adj(ctx.db, pid, kind, float(m.group(1).replace(",", ".")), day, source="manual",
              note=m.group(2).strip()[:120])
    r.args = [str(pid), key]
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
        sub = K.stand_in(db, pid, a["day"]) if a["kind"] in ("fine", "bonus") and a["source"] in K.MOVABLE else None
        to = f" → {P.person(db, sub)['name']}" if sub else ""      # o'rniga ishlaganga o'tgan
        rows.append([(f"{mark} {a['day'][8:10]}.{a['day'][5:7]} · {word.get(a['kind'], '?')} {money(a['usd'])} $"
                      f"{to} · {(a['note'] or a['source'])[:18]}", f"pa:{pid}:{a['id']}")])
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
        return r.L("🧮 Avval haftani hisoblang (Kassa → 🧮 Haftalik zp)",
                   "🧮 Сначала рассчитайте неделю (Касса → 🧮 Зп за неделю)")
    row = K.calc(db, s, e)["rows"].get(pid)
    if row is None:
        return r.L("Ma'lumot yo'q", "Данных нет")
    from .score import worker_stats
    msg = worker_message(row, s, e, worker_stats(ctx, pid, s, e))
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
        from .score import worker_stats
        await ctx.bot.send_message(p["tg_id"], worker_message(row, s, e, worker_stats(ctx, pid, s, e)))
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
    _s, e, key = period_of(ctx, r, pid, key)
    e = min(e, today(ctx))                                 # kelajak kunlar «berildi» bo'lmaydi
    s, _e = K.open_period(ctx.db, pid, e)                  # belgilanadigan hisob — oxirgi oylikdan (ppy bilan bir xil)
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
    r.args = ui.last_args(r, "po", str(pid)) or [str(pid)]
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
                 ((r.L("🙋 Nazoratni o'chirish", "🙋 Контроль: выкл") if p["attend"] else r.L("🙋 Nazoratni yoqish",
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
        if kind == "self":                             # 👑 Ega — shu akkaunt botda to'liq ega (egasi, 2026-11-12)
            r.args = [str(pid)]
            return await make_owner(ctx, r)
        if kind and not db.one("SELECT 1 FROM pct WHERE person_id=?", (pid,)):
            K.set_percent(db, pid, 50 if kind in ("self", "partner") else 30, "2000-01-01")
        P.update_person(db, pid, kassa_kind=kind)
        return await person_settings(ctx, r)
    opts = [("none", r.L("👤 Faqat nazorat (kassasiz)", "👤 Только контроль (без кассы)")),
            ("worker", r.L("💼 Kassa xodimi (foiz bilan)", "💼 Обработчик (с процентом)")),
            ("pool", r.L("🔁 Umumiy akkaunt", "🔁 Общий аккаунт"))]
    if r.owner:
        opts += [("partner", r.L("🤝 Hamkor (kassadan %)", "🤝 Партнёр (% от кассы)")),
                 ("self", r.L("👑 Ega (siz) — botda to'liq", "👑 Владелец (вы) — полный доступ"))]
    cur = p["kassa_kind"] or "none"
    rows = [[(("● " if k == cur else "○ ") + t, f"psk:{pid}:{k}")] for k, t in opts]
    rows.append(nav(r, f"ps:{pid}"))
    return title("🏷", h(p["name"]), r.L("turi", "тип")), kb(*rows)


@screen("psko", "owner")
async def make_owner(ctx, r: Req):
    """👑 Ega (egasi, 2026-11-12: «egani bossam — u botda 100% foydalana olsin, yo'qolgan akkauntim qanday bo'lsa —
    xuddi shunday»): shu Telegram akkaunt botda to'liq ega bo'ladi. Kassadagi «👑 siz» yozuvi boshqa bo'lsa — bu yozuv
    unga qo'shiladi va «siz» yozuvi shu (yangi) akkauntga o'tadi: kassa va zp tarixi o'sha yerda qoladi."""
    db = ctx.db
    pid = int(r.args[0])
    x = must(P.person(db, pid))
    me = db.one("SELECT * FROM people WHERE kassa_kind='self' AND active=1 AND id<>? ORDER BY id LIMIT 1", (pid,))
    nm = h(x["name"])
    who = f"@{h(x['username'])}" if x["username"] else (f"🆔 {x['tg_id']}" if x["tg_id"] else "")
    if not x["username"] and not x["tg_id"]:
        return ui.join(title("👑", nm, r.L("ega", "владелец")), "", card([r.L(
            "Avval shu akkauntning @username ini yozing — bot uni ega qiladi.",
            "Сначала укажите @username этого аккаунта — бот сделает его владельцем.")])), \
            kb([("✈️ @username", f"pse:{pid}:user")], nav(r, f"psk:{pid}"))
    if len(r.args) < 2 or r.args[1] != "y":
        lines = [r.L(f"<b>{nm}</b> ({who}) botda to'liq ega bo'ladi — eski akkauntingiz kabi: hamma narsani ko'radi "
                     f"va o'zgartiradi (kassa, zp, Push, sozlamalar).",
                     f"<b>{nm}</b> ({who}) станет полным владельцем в боте — как ваш старый аккаунт: видит и меняет "
                     f"всё (касса, зп, Пуш, настройки).")]
        if me is not None:
            lines.append(r.L(f"Kassadagi «{h(me['name'])}» (siz) yozuvi shu akkauntga o'tadi — kassa va zp "
                             f"tarixingiz o'sha yerda qoladi. «{nm}» yozuvi unga qo'shiladi.",
                             f"Запись «{h(me['name'])}» (вы) в кассе перейдёт на этот аккаунт — история кассы и зп "
                             f"остаётся там. Запись «{nm}» войдёт в неё."))
        if not x["tg_id"]:
            lines.append(r.L(f"{who} botga /start bossin — shunda ega bo'ladi (7 kun ichida).",
                             f"Пусть {who} нажмёт /start у бота — тогда станет владельцем (в течение 7 дней)."))
        return ui.join(title("👑", nm, r.L("yangi akkauntingiz", "ваш новый аккаунт")), "", card(lines)), \
            kb([(r.L("✅ Ha, bu mening yangi akkauntim", "✅ Да, это мой новый аккаунт"), f"psko:{pid}:y")],
               nav(r, f"psk:{pid}"))
    tg, u = x["tg_id"], x["username"]
    old_tg, target = None, pid
    if me is not None:
        old_tg = me["tg_id"]
        db.run("UPDATE people SET tg_id=NULL, username='' WHERE id=?", (me["id"],))   # eski akkaunt uziladi
        P.merge_people(db, me["id"], pid)              # yozuv «siz»ga qo'shiladi; Telegram — yangi akkaunt
        target = me["id"]
    else:
        P.update_person(db, pid, kassa_kind="self")
        if not db.one("SELECT 1 FROM pct WHERE person_id=?", (pid,)):
            K.set_percent(db, pid, 50, "2000-01-01")
    name = (P.person(db, target) or x)["name"]
    if tg:
        P.set_admin(db, int(tg), "owner", name)
        from .panel import set_commands
        await set_commands(ctx, int(tg))
        try:
            await ctx.bot.send_message(int(tg), "👮 /menu")
        except Exception:
            pass
        lines = [r.L(f"✅ {who} — endi botda to'liq ega.", f"✅ {who} — теперь полный владелец в боте.")]
    else:
        P.add_pending_admin(db, u, "owner", name, pid=target)
        lines = [r.L(f"⏳ {who} botga /start bossin — shu zahoti to'liq ega bo'ladi (sizga xabar keladi).",
                     f"⏳ Пусть {who} нажмёт /start у бота — сразу станет владельцем (вам придёт сообщение).")]
    rows = []
    if old_tg and old_tg != tg:
        lines.append(r.L(f"Eski akkaunt (🆔 {old_tg}) «{h(name)}» yozuvidan uzildi.",
                         f"Старый аккаунт (🆔 {old_tg}) отвязан от записи «{h(name)}»."))
        if old_tg in ctx.cfg.owner_ids:
            lines.append(r.L("U Railway → ADMIN_IDS da turibdi — kerak bo'lmasa, o'sha yerdan olib tashlang.",
                             "Он в Railway → ADMIN_IDS — если не нужен, уберите его оттуда."))
        elif old_tg != r.uid and db.one("SELECT 1 FROM admins WHERE user_id=?", (old_tg,)):
            rows.append([(r.L("🗑 Eski akkauntni adminlikdan olib tashlash", "🗑 Убрать старый аккаунт из админов"),
                          f"sd:x:{old_tg}")])
    rows.append([(f"👑 {name} — {r.L('kabinet', 'кабинет')}", f"po:{target}")])
    rows.append(nav(r, "p"))
    return ui.join(title("👑", h(name), r.L("ega", "владелец")), "", card(lines)), kb(*rows)


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
        old = (P.person(db, pid) or {"name": ""})["name"]
        P.update_person(db, pid, name=text)
        K.rename_opening(db, old, text)                    # umumiy reytingdagi boshlang'ich kassa ham shu ismga
    elif field == "user":
        u = "" if text in ("-", "—") else P.norm_username(text)
        if u and not P.valid_username(u):
            return r.L("⚠️ @username noto'g'ri", "⚠️ Неверный @username")
        other = P.by_username(db, u) if u else None
        if other is not None and other["id"] != pid:
            ui.WAIT.pop(r.uid, None)
            me = must(P.person(db, pid))
            return ui.join(title("🔗", r.L("BU @USERNAME BOSHQA YOZUVDA", "ЭТОТ @USERNAME В ДРУГОЙ ЗАПИСИ")), "", card(
                [r.L(f"@{h(u)} — «{h(other['name'])}» yozuvida. Bitta odam bo'lsa — birlashtiring: «{h(other['name'])}» "
                     f"«{h(me['name'])}»ga qo'shiladi (kassa, jarima, papkalar, Telegram).",
                     f"@{h(u)} — в записи «{h(other['name'])}». Если это один человек — объедините: «{h(other['name'])}» "
                     f"войдёт в «{h(me['name'])}» (касса, штрафы, папки, Telegram).")])), \
                kb([(r.L("🔗 Birlashtirish", "🔗 Объединить"), f"psmy:{pid}:{other['id']}")], nav(r, f"ps:{pid}"))
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
    if P.person(ctx.db, drop) is not None:
        P.merge_people(ctx.db, keep, drop)
        ctx.tracker.reload()
        if ctx.userbot is not None:
            ctx.userbot.reload_ids()
        await ui.toast(ctx.bot, r.chat_id, r.L("🔗 Birlashtirildi", "🔗 Объединено"))
    await ctx.notifier.resolve(f"tw:{keep}x{drop}", skip=((r.chat_id, getattr(r.message, "message_id", 0)),))
    r.args = [str(keep)]
    return await person_settings(ctx, r)
