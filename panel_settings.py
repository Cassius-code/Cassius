"""⚙️ Sozlamalar: «Проёб» guruhi, akkauntlar (asosiy va Push), adminlar, ishga kelish va tanaffus, kassa
ma'lumotini ko'chirish, zaxira nusxa, chat qidirish, botni to'xtatish."""
from __future__ import annotations

import os
import re
import time

from . import people as P
from .kassa import zp_mode
from . import ui
from .tgclient import LoginFlow
from .timeutil import parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title

STATE_UZ = {"online": "🟢 ulangan", "connecting": "🟡 ulanmoqda…", "starting": "🟡 ishga tushmoqda…",
            "offline": "🔴 aloqa yo'q", "unauthorized": "🔴 qayta kirish kerak", "no_session": "⚪ ulanmagan",
            "disabled": "⚪ API_ID / API_HASH yo'q", "paused": "⏸ pauzada"}
STATE_RU = {"online": "🟢 подключён", "connecting": "🟡 подключается…", "starting": "🟡 запускается…",
            "offline": "🔴 нет связи", "unauthorized": "🔴 нужен вход", "no_session": "⚪ не подключён",
            "disabled": "⚪ нет API_ID / API_HASH", "paused": "⏸ на паузе"}


def st(r: Req, state: str) -> str:
    return (STATE_RU if r.lang == "ru" else STATE_UZ).get(state, state)


@screen("s", "full")
async def settings(ctx, r: Req):
    db = ctx.db
    ub = ctx.userbot
    accs = db.all("SELECT * FROM accounts ORDER BY id")
    lines = [f"⏯ {r.L('Bot', 'Бот')} — {onoff(r, db.flag('bot_enabled'))}",
             f"🔑 {r.L('Asosiy akkaunt', 'Основной аккаунт')} — {st(r, ub.state if ub else 'disabled')}"
             + (f" · {h(ub.me_label)}" if ub and ub.me_label else ""),
             f"📲 {r.L('Push akkauntlar', 'Push-аккаунты')} — <b>{len(accs)}</b>",
             "👥 «Проёб» — " + (f"<code>{h(db.get('proyob_group_id'))}</code>" if db.get("proyob_group_id")
                                else r.L("belgilanmagan ⚠️", "не задана ⚠️")),
             f"💸 {r.L('Avto-jarimalar', 'Авто-штрафы')} — {onoff(r, db.flag('fines_enabled'))}",
             f"🧮 {r.L('Zp hisoblash', 'Расчёт зп')} — " + {"button": r.L("tugma bilan", "по кнопке"),
                                                           "auto": r.L("avtomatik", "автоматически"),
                                                           "off": r.L("o'chiq", "выключен")}[zp_mode(db)],
             f"🙋 {r.L('Ishga kelish', 'Приход')} — {onoff(r, db.flag('attendance_enabled'))} · "
             f"☕ {r.L('Tanaffus', 'Перерывы')} — {onoff(r, db.flag('breaks_enabled'))}"]
    btn = [(r.L("👥 «Проёб» guruhi", "👥 Группа «Проёб»"), "sg"), (r.L("🔑 Asosiy akkaunt", "🔑 Основной аккаунт"), "sm"),
           (r.L("📲 Push akkauntlar", "📲 Push-аккаунты"), "sa"), (r.L("👮 Adminlar", "👮 Админы"), "sd"),
           (r.L("🙋 Ishga kelish", "🙋 Приход"), "st"), (r.L("☕ Tanaffus", "☕ Перерывы"), "sr"),
           (r.L("📥 Ko'chirish", "📥 Перенос данных"), "sk"), (r.L("💾 Zaxira nusxa", "💾 Резервная копия"), "sb"),
           (r.L("🔎 Chat qidirish", "🔎 Поиск чата"), "sx")]
    if r.owner:
        btn.append((r.L("🧮 Zp hisoblash", "🧮 Расчёт зп"), "kzm"))
        btn.append((r.L("🧹 Tozalash", "🧹 Очистка"), "sz"))
    rows = grid(btn)
    rows.append([((r.L("💸 Jarimalarni o'chirish", "💸 Выключить штрафы") if db.flag("fines_enabled") else
                   r.L("💸 Jarimalarni yoqish", "💸 Включить штрафы")), "sfn")])
    rows.append([((r.L("⛔ Botni to'xtatish", "⛔ Остановить бота") if db.flag("bot_enabled") else
                   r.L("▶️ Botni yoqish", "▶️ Включить бота")), "so", "danger" if db.flag("bot_enabled") else "success")])
    rows.append(nav(r))
    text = ui.join(title("⚙️", r.L("SOZLAMALAR", "НАСТРОЙКИ")), "", card(lines))
    from . import panel_cards as PC
    alive = db.flag("bot_enabled")
    ub_ok = bool(ub and ub.state == "online")
    online = sum(1 for a in accs if ctx.pool and ctx.pool.state_of(a["id"]) == "online")
    zp = {"button": r.L("tugma bilan", "по кнопке"), "auto": r.L("avtomatik", "авто"),
          "off": r.L("o'chiq", "выкл")}[zp_mode(db)]
    srows = [(r.L("Asosiy akkaunt", "Основной аккаунт"), (ub.me_label if ub and ub.me_label else "")[:22] or
              (r.L("ulangan", "подключён") if ub_ok else r.L("ulanmagan", "не подключён")), "🔑"),
             (r.L("Push akkauntlar", "Push-аккаунты"), f"{online} / {len(accs)}", "📲"),
             (r.L("Avto-jarimalar", "Авто-штрафы"), PC.onoff(r, db.flag("fines_enabled")), "💸"),
             (r.L("Zp hisoblash", "Расчёт зп"), zp, "🧮"),
             (r.L("Ishga kelish", "Приход"), PC.onoff(r, db.flag("attendance_enabled")), "🙋"),
             (r.L("Tanaffus", "Перерывы"), PC.onoff(r, db.flag("breaks_enabled")), "☕")]
    chips = [(r.L("Bot", "Бот"), alive), (r.L("Akkaunt", "Аккаунт"), ub_ok),
             ("«Проёб»", bool(db.get("proyob_group_id")))]
    return ui.rich(text, PC.settings(r, alive, srows, chips)), kb(*rows)


WIPE = {"kassa": ("🧾", "Kassa yozuvlari", "Записи кассы",
                  "cheklar, hisobotlar, jarima/bonus/avans, to'lovlar, ulushlar, haftalik foizlar, tarix",
                  "чеки, отчёты, штрафы/бонусы/авансы, выплаты, доли, недельные проценты, история"),
        "people": ("👥", "Xodimlar (kassa ham)", "Сотрудники (и касса)",
                   "hamma xodimlar, foizlari, papkadagi o'rni, ishga kelish — va hamma kassa yozuvlari",
                   "все сотрудники, проценты, места в папках, приход — и все записи кассы"),
        "push": ("📲", "Push akkauntlar", "Push-аккаунты", "Push akkauntlar (qayta kirasiz)",
                 "Push-аккаунты (войдёте заново)"),
        "all": ("🧹", "Hammasi", "Всё", "kassa, xodimlar va Push akkauntlar", "касса, сотрудники и Push-аккаунты")}


@screen("sz", "owner")
async def wipe_screen(ctx, r: Req):
    db = ctx.db
    a = r.args
    keep = r.L("Qoladi: prays, sozlamalar, papkalar, chatlar, adminlar, asosiy akkaunt, boshlang'ich kassa.",
               "Остаётся: прайс, настройки, папки, чаты, админы, основной аккаунт, начальная касса.")
    if a and a[0] in WIPE and len(a) > 1 and a[1] == "y":
        P.wipe(db, a[0])
        from .kassa import log
        log(db, "wipe", None, None, None, "", a[0])
        for pfx in ("qr:", "qa:", "qp:", "sup:", "dup:", "kn:", "kcl:", "adjmiss:"):
            for row in db.all("SELECT DISTINCT key FROM sent WHERE key LIKE ?", (pfx + "%",)):
                if a[0] != "push":
                    await ctx.notifier.resolve(row["key"])
        ctx.tracker.reload()
        if ctx.userbot is not None:
            ctx.userbot.reload_ids()
        if ctx.pool is not None:
            ctx.pool.sync()
        icon, uz, ru, _du, _dr = WIPE[a[0]]
        await ui.toast(ctx.bot, r.chat_id, r.L(f"🧹 Tozalandi: {uz}", f"🧹 Очищено: {ru}"), 6)
        r.args = []
        return await settings(ctx, r)
    if a and a[0] in WIPE:
        icon, uz, ru, du, dr = WIPE[a[0]]
        return ui.join(title(icon, r.L("ROSTDAN HAM O'CHIRILSINMI?", "ТОЧНО УДАЛИТЬ?"), r.L(uz, ru)), "",
                       card([r.L(f"O'chadi: {du}.", f"Удалится: {dr}."), keep,
                             r.L("Qaytarib bo'lmaydi. Kerak bo'lsa avval ⚙️ → 💾 Zaxira nusxa oling.",
                                 "Вернуть нельзя. Если нужно — сначала ⚙️ → 💾 Резервная копия.")])), \
            kb([(r.L("🧹 Ha, o'chirish", "🧹 Да, удалить"), f"sz:{a[0]}:y")], [(r.L("✖️ Yo'q", "✖️ Нет"),
                                                                              ui.back_data("sz"))])
    counts = [f"🧾 {r.L('Cheklar', 'Чеки')} — <b>{db.scalar('SELECT COUNT(*) FROM checks')}</b>",
              f"👥 {r.L('Xodimlar', 'Сотрудники')} — <b>{db.scalar('SELECT COUNT(*) FROM people')}</b>",
              f"📲 Push — <b>{db.scalar('SELECT COUNT(*) FROM accounts')}</b>"]
    rows = [[(f"{v[0]} {r.L(v[1], v[2])}", f"sz:{k}")] for k, v in WIPE.items()]
    rows.append(nav(r, "s"))
    return ui.join(title("🧹", r.L("TOZALASH", "ОЧИСТКА"), r.L("boshidan kiritish uchun", "чтобы ввести заново")),
                   "", card(counts), card([keep])), kb(*rows)


@screen("sfn", "full")
async def fines_toggle(ctx, r: Req):
    on = ctx.db.toggle("fines_enabled")
    await ui.toast(ctx.bot, r.chat_id, r.L("💸 Avto-jarimalar yoqildi" if on else "💸 Avto-jarimalar o'chirildi",
                                           "💸 Авто-штрафы включены" if on else "💸 Авто-штрафы выключены"))
    return await settings(ctx, r)


@screen("so", "owner")
async def bot_toggle(ctx, r: Req):
    ctx.db.toggle("bot_enabled")
    return await settings(ctx, r)


# ───────────────────────── «Проёб» guruhi
@screen("sg", "full")
async def group(ctx, r: Req):
    ui.ask(r, "group_id", "s")
    cur = ctx.db.get("proyob_group_id")
    return ui.join(title("👥", r.L("«ПРОЁБ» GURUHI", "ГРУППА «ПРОЁБ»")), "", card(
        [r.L(f"Hozir: <code>{h(cur) or '—'}</code>", f"Сейчас: <code>{h(cur) or '—'}</code>"),
         r.L("<b>Eng osoni:</b> botni guruhga qo'shing, admin qiling va guruhning o'zida <code>/proyob</code> yozing.",
             "<b>Проще всего:</b> добавьте бота в группу, сделайте админом и напишите в группе <code>/proyob</code>."),
         r.L("Yoki guruh ID sini shu yerga yuboring (<code>-100…</code>).", "Или пришлите сюда ID группы (<code>-100…</code>).")])), \
        ui.cancel_kb(r, "s")


@on_input("group_id")
async def group_set(ctx, r: Req):
    m = re.search(r"-\d{6,}", r.text)
    if not m:
        return r.L("⚠️ Guruh ID si manfiy son (-100…)", "⚠️ ID группы — отрицательное число (-100…)")
    ctx.db.set("proyob_group_id", m.group(0))
    return await settings(ctx, r)


# ───────────────────────── asosiy akkaunt va login
@screen("sm", "full")
async def main_account(ctx, r: Req):
    ub = ctx.userbot
    lines = [f"{r.L('Holati', 'Состояние')} — {st(r, ub.state)}"]
    if ub.me_label:
        lines.append(f"👤 {h(ub.me_label)}")
    if ub.last_sync:
        lines.append(r.L("Oxirgi sinxron: ", "Последняя синхронизация: ") + time.strftime(
            "%H:%M", time.localtime(ub.last_sync)))
    lines.append(r.L("Asosiy akkaunt ish chatlarini kuzatadi (faqat kim/qachon). Push yubormaydi.",
                     "Основной аккаунт следит за чатами (только кто/когда). Push не шлёт."))
    rows = [[(r.L("📲 Ulash / almashtirish", "📲 Подключить / сменить"), "sml:main")],
            [(r.L("🔄 Yangilash (papka, chat, xabarlar)", "🔄 Обновить (папки, чаты, сообщения)"), "sms")]]
    if ub.session():
        rows.append([(r.L("🚪 Uzish", "🚪 Отключить"), "smo")])
    rows.append(nav(r, "s"))
    return ui.join(title("🔑", r.L("ASOSIY AKKAUNT", "ОСНОВНОЙ АККАУНТ")), "", card(lines)), kb(*rows)


@screen("sms", "full")
async def main_sync(ctx, r: Req):
    if ctx.userbot.state != "online":
        return r.L("⚠️ Akkaunt ulanmagan", "⚠️ Аккаунт не подключён")
    ui.bg(ctx.userbot.sync_all())
    await ui.toast(ctx.bot, r.chat_id, r.L("🔄 Yangilanmoqda…", "🔄 Обновляю…"))
    return await main_account(ctx, r)


@screen("smo", "owner")
async def main_logout(ctx, r: Req):
    if len(r.args) and r.args[0] == "y":
        await ctx.userbot.logout()
        return await main_account(ctx, r)
    return title("🚪", r.L("UZISHMI?", "ОТКЛЮЧИТЬ?")) + "\n\n" + card(
        [r.L("Kuzatuv to'xtaydi.", "Контроль остановится.")]), \
        kb([(r.L("✅ Ha", "✅ Да"), "smo:y"), (r.L("✖️ Yo'q", "✖️ Нет"), "sm")])


@screen("sml", "full")
async def login_start(ctx, r: Req):
    target = r.args[0] if r.args else "main"
    if not (ctx.cfg.api_id and ctx.cfg.api_hash):
        return r.L("⚠️ Railway'da API_ID va API_HASH berilmagan", "⚠️ В Railway не заданы API_ID и API_HASH")
    ui.ask(r, "login_phone", "s", target=target)
    what = r.L("asosiy akkaunt", "основной аккаунт") if target == "main" else r.L("yangi Push akkaunt",
                                                                                   "новый Push-аккаунт")
    return title("📲", r.L("ULASH", "ПОДКЛЮЧЕНИЕ"), what) + "\n\n" + card(
        [r.L("Telefon raqamini yuboring, masalan <code>+998901234567</code>.",
             "Пришлите номер телефона, например <code>+998901234567</code>.")]), ui.cancel_kb(r, "s")


@on_input("login_phone")
async def login_phone(ctx, r: Req, target: str):
    phone = re.sub(r"[^\d+]", "", r.text)
    if len(phone) < 9:
        return r.L("⚠️ Raqam noto'g'ri", "⚠️ Неверный номер")
    flow = LoginFlow(ctx.cfg.api_id, ctx.cfg.api_hash)
    try:
        await flow.start(phone)
    except Exception as exc:
        await flow.cancel()
        return r.L(f"⚠️ Kod yuborilmadi: {h(type(exc).__name__)}", f"⚠️ Код не отправлен: {h(type(exc).__name__)}")
    ctx.login[r.uid] = flow
    ui.ask(r, "login_code", "s", target=target)
    return title("🔐", r.L("KOD", "КОД")) + "\n\n" + card(
        [r.L("Telegram yuborgan kodni <b>bo'shliq bilan</b> yozing: <code>1 2 3 4 5</code> "
             "(aks holda Telegram kodni bloklaydi).",
             "Напишите код из Telegram <b>через пробелы</b>: <code>1 2 3 4 5</code> (иначе Telegram заблокирует код).")]), \
        ui.cancel_kb(r, "s")


@on_input("login_code")
async def login_code(ctx, r: Req, target: str):
    flow = ctx.login.get(r.uid)
    if flow is None:
        return r.L("⚠️ Qaytadan boshlang", "⚠️ Начните заново")
    code = re.sub(r"\D", "", r.text)
    try:
        res = await flow.submit_code(code)
    except Exception as exc:
        return r.L(f"⚠️ Kod noto'g'ri: {h(type(exc).__name__)}", f"⚠️ Неверный код: {h(type(exc).__name__)}")
    if res == "password":
        ui.ask(r, "login_pass", "s", target=target)
        return title("🔐", r.L("PAROL", "ПАРОЛЬ")) + "\n\n" + card(
            [r.L("Ikki bosqichli parolni yuboring (xabar darhol o'chiriladi).",
                 "Пришлите пароль двухэтапной проверки (сообщение сразу удалится).")]), ui.cancel_kb(r, "s")
    return await login_done(ctx, r, target)


@on_input("login_pass")
async def login_pass(ctx, r: Req, target: str):
    flow = ctx.login.get(r.uid)
    if flow is None:
        return r.L("⚠️ Qaytadan boshlang", "⚠️ Начните заново")
    try:
        await flow.submit_password(r.text)
    except Exception as exc:
        return r.L(f"⚠️ Parol noto'g'ri: {h(type(exc).__name__)}", f"⚠️ Неверный пароль: {h(type(exc).__name__)}")
    return await login_done(ctx, r, target)


async def login_done(ctx, r: Req, target: str):
    flow = ctx.login.pop(r.uid)
    session = flow.session_string()
    await flow.cancel()
    if target == "main":
        await ctx.userbot.set_session(session)
        await ui.toast(ctx.bot, r.chat_id, r.L("✅ Asosiy akkaunt ulandi", "✅ Основной аккаунт подключён"))
        return await main_account(ctx, r)
    n = ctx.db.scalar("SELECT COUNT(*) FROM accounts") + 1
    ctx.db.run("INSERT INTO accounts(name, session, added_ts) VALUES(?,?,?)", (f"Push {n}", session, int(time.time())))
    ctx.pool.sync()
    await ui.toast(ctx.bot, r.chat_id, r.L("✅ Push akkaunt qo'shildi", "✅ Push-аккаунт добавлен"))
    return await accounts(ctx, r)


# ───────────────────────── Push akkauntlar
@screen("sa", "full")
async def accounts(ctx, r: Req):
    db = ctx.db
    if r.args:
        return await account_card(ctx, r)
    rows = []
    for a in db.all("SELECT * FROM accounts ORDER BY id"):
        state = ctx.pool.state_of(a["id"]) if ctx.pool else "no_session"
        icon = {"online": "🟢", "paused": "⏸"}.get(state, "🔴" if state in ("offline", "unauthorized") else "🟡")
        rows.append([(f"{icon} {a['name']} {a['label']}"[:50], f"sa:{a['id']}")])
    rows.append([(r.L("➕ Push akkaunt qo'shish", "➕ Добавить Push-аккаунт"), "sml:push")])
    rows.append(nav(r, "s"))
    return ui.join(title("📲", r.L("PUSH AKKAUNTLAR", "PUSH-АККАУНТЫ")), "", card(
        [r.L("Har papkaga o'z akkaunti (📣 Push → 📁 Papkalar). Akkaunt kerakli chatlarda bo'lishi kerak.",
             "У каждой папки свой аккаунт (📣 Push → 📁 Папки). Аккаунт должен быть в нужных чатах.")])), kb(*rows)


async def account_card(ctx, r: Req):
    db = ctx.db
    aid = int(r.args[0])
    if len(r.args) > 1:
        op = r.args[1]
        if op == "p":
            a = db.one("SELECT paused FROM accounts WHERE id=?", (aid,))
            db.run("UPDATE accounts SET paused=? WHERE id=?", (0 if a["paused"] else 1, aid))
            ctx.pool.sync()
        elif op == "n":
            ui.ask(r, "acc_name", f"sa:{aid}", aid=aid)
            return title("✏️", r.L("AKKAUNT NOMI", "НАЗВАНИЕ")) + "\n\n" + card(
                [r.L("Yangi nom (30 belgigacha).", "Новое название (до 30 символов).")]), ui.cancel_kb(r, f"sa:{aid}")
        elif op == "x":
            return title("🗑", r.L("O'CHIRILSINMI?", "УДАЛИТЬ?")) + "\n\n" + card(
                [r.L("Papkalar akkauntsiz qoladi.", "Папки останутся без аккаунта.")]), \
                kb([(r.L("✅ Ha", "✅ Да"), f"sa:{aid}:y"), (r.L("✖️ Yo'q", "✖️ Нет"), f"sa:{aid}")])
        elif op == "y":
            db.run("UPDATE folders SET push_account_id=NULL WHERE push_account_id=?", (aid,))
            db.run("DELETE FROM accounts WHERE id=?", (aid,))
            ctx.pool.sync()
            r.args = []
            return await accounts(ctx, r)
    a = db.one("SELECT * FROM accounts WHERE id=?", (aid,))
    if a is None:
        r.args = []
        return await accounts(ctx, r)
    used = [f["name"] for f in db.all("SELECT name FROM folders WHERE push_account_id=?", (aid,))]
    lines = [f"{r.L('Holati', 'Состояние')} — {st(r, ctx.pool.state_of(aid))}", f"👤 {h(a['label'] or '—')}",
             f"📁 {h(', '.join(used) or r.L('papka yo‘q', 'нет папок'))}"]
    rows = grid([((r.L("▶️ Davom ettirish", "▶️ Возобновить") if a["paused"] else r.L("⏸ Pauza", "⏸ Пауза")),
                  f"sa:{aid}:p"), (r.L("✏️ Nomi", "✏️ Название"), f"sa:{aid}:n"),
                 (r.L("🗑 O'chirish", "🗑 Удалить"), f"sa:{aid}:x")])
    rows.append(nav(r, "sa"))
    return ui.join(title("📲", h(a["name"])), "", card(lines)), kb(*rows)


@on_input("acc_name")
async def account_rename(ctx, r: Req, aid: int):
    name = r.text.strip()[:30]
    if not name:
        return r.L("⚠️ Nom kerak", "⚠️ Нужно название")
    ctx.db.run("UPDATE accounts SET name=? WHERE id=?", (name, aid))
    r.args = [str(aid)]
    return await account_card(ctx, r)


# ───────────────────────── adminlar
LEVEL_UZ = {"owner": "👑 ega", "full": "🛠 to'liq", "view": "👁 faqat ko'radi"}
LEVEL_RU = {"owner": "👑 владелец", "full": "🛠 полный", "view": "👁 только просмотр"}


@screen("sd", "full")
async def admins(ctx, r: Req):
    db = ctx.db
    names = LEVEL_RU if r.lang == "ru" else LEVEL_UZ
    a = r.args
    if a and a[0] == "l" and r.owner:                     # darajani almashtirish
        uid = int(a[1])
        row = db.one("SELECT * FROM admins WHERE user_id=?", (uid,))
        if row:
            order = ["view", "full", "owner"]
            P.set_admin(db, uid, order[(order.index(row["level"]) + 1) % 3])
    if a and a[0] == "x" and r.owner:
        P.del_admin(db, int(a[1]))
    lines = [f"👑 <code>{u}</code> · Railway" for u in ctx.cfg.owner_ids]
    rows = []
    for ad in P.admins(db):
        lines.append(f"{names.get(ad['level'], ad['level'])} · {h(ad['name'] or ad['user_id'])}")
        if r.owner:
            rows.append([(f"🔁 {ad['name'] or ad['user_id']} · {names.get(ad['level'])}", f"sd:l:{ad['user_id']}"),
                         ("🗑", f"sd:x:{ad['user_id']}")])
    if r.owner:
        from . import recovery
        rows.append([(r.L("➕ ID bo'yicha admin", "➕ Админ по ID"), "sdn")])
        rows.append([(r.L("🔐 Tiklash kodi", "🔐 Код восстановления"), "sdr")])
        ts = db.get("recovery_ts")
        lines.append("")
        lines.append(f"🔐 {r.L('Tiklash kodi', 'Код восстановления')} — " +
                     (r.L(f"o'rnatilgan ({time.strftime('%d.%m.%Y', time.localtime(int(ts)))})",
                          f"задан ({time.strftime('%d.%m.%Y', time.localtime(int(ts)))})")
                      if recovery.is_set(db) and ts else r.L("yo'q ⚠️", "нет ⚠️")))
    rows.append(nav(r, "s"))
    return ui.join(title("👮", r.L("ADMINLAR", "АДМИНЫ")), "", card(lines), card(
        [r.L("👑 ega — hammasi (ulushingiz ham) · 🛠 to'liq — boshqaruv, ulushingizni ko'rmaydi · 👁 — faqat ko'radi. "
             "Bosing — darajani almashtirish.",
             "👑 владелец — всё (и ваша доля) · 🛠 полный — управление, без вашей доли · 👁 — только просмотр. "
             "Нажмите — сменить уровень.")])), kb(*rows)


@screen("sdr", "owner")
async def recovery_screen(ctx, r: Req):
    from . import recovery
    if r.args and r.args[0] == "x":
        recovery.clear(ctx.db)
        r.args = []
        return await admins(ctx, r)
    ui.ask(r, "recovery_code", "sd")
    lines = [r.L("Agar Telegram akkauntingiz yo'qolsa yoki o'chib ketsa — yangi akkauntdan botga yozasiz:",
                 "Если ваш Telegram-аккаунт пропадёт или удалится — с нового аккаунта пишете боту:"),
             r.L("<code>/ega KODINGIZ</code> → o'sha akkaunt 👑 ega bo'ladi.",
                 "<code>/ega ВАШ_КОД</code> → этот аккаунт станет 👑 владельцем."),
             "",
             r.L("Kamida 8 belgili kod yozing. Xabaringiz darhol o'chadi, bazada faqat shifrlangan izi qoladi.",
                 "Напишите код минимум из 8 символов. Сообщение сразу удалится, в базе — только зашифрованный след."),
             r.L("Kod bir marta ishlaydi. Uni qog'ozga yozib, xavfsiz joyda saqlang — Telegram'da saqlamang.",
                 "Код одноразовый. Запишите его на бумаге и храните надёжно — не в Telegram.")]
    rows = []
    if recovery.is_set(ctx.db):
        rows.append([(r.L("🗑 Kodni o'chirish", "🗑 Удалить код"), "sdr:x")])
    rows.append([(r.L("✖️ Bekor qilish", "✖️ Отмена"), "sd")])
    return ui.join(title("🔐", r.L("TIKLASH KODI", "КОД ВОССТАНОВЛЕНИЯ")), "", card(lines)), kb(*rows)


@on_input("recovery_code", "owner")
async def recovery_set(ctx, r: Req):
    from . import recovery
    code = r.text.strip()
    if len(code) < recovery.MIN_LEN or " " in code:
        return r.L("⚠️ Kamida 8 belgi, bo'sh joysiz", "⚠️ Минимум 8 символов, без пробелов")
    recovery.set_code(ctx.db, code)
    ui.WAIT.pop(r.uid, None)
    await ui.toast(ctx.bot, r.chat_id, r.L("🔐 Kod saqlandi. Uni qog'ozga yozib qo'ying.",
                                           "🔐 Код сохранён. Запишите его на бумаге."), 8)
    r.args = []
    return await admins(ctx, r)


@screen("sdn", "owner")
async def admin_add_ask(ctx, r: Req):
    ui.ask(r, "admin_add", "sd")
    return title("➕", r.L("YANGI ADMIN", "НОВЫЙ АДМИН")) + "\n\n" + card(
        [r.L("Telegram ID sini yuboring (u botga /id yozib bilib oladi). Boshida «🛠 to'liq».",
             "Пришлите Telegram ID (он узнает через /id у бота). По умолчанию «🛠 полный».")]), ui.cancel_kb(r, "sd")


@on_input("admin_add", "owner")
async def admin_add(ctx, r: Req):
    m = re.search(r"\d{5,}", r.text)
    if not m:
        return r.L("⚠️ ID — son", "⚠️ ID — число")
    P.set_admin(ctx.db, int(m.group(0)), "full")
    try:
        await ctx.bot.send_message(int(m.group(0)), "👮 /menu")
    except Exception:
        pass
    r.args = []
    return await admins(ctx, r)


# ───────────────────────── ishga kelish va tanaffus
@screen("st", "full")
async def attendance(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] == "t":
        db.toggle("attendance_enabled")
    from .attendance import late_fine_text
    lines = [f"🙋 {r.L('Nazorat', 'Контроль')} — {onoff(r, db.flag('attendance_enabled'))}",
             f"🕘 {r.L('Ish boshlanishi', 'Начало работы')} — <b>{db.get('work_start')}</b>",
             f"⏰ {r.L('Eslatma', 'Напоминание')} — {r.L('boshlanib', 'через')} <b>{db.get('noshow_minutes')}</b> "
             f"{r.L('daqiqa o‘tsa', 'мин после начала')}",
             f"💸 {r.L('Kech qolish', 'Опоздание')} — <b>{h(late_fine_text(db.get('late_fine'), r.lang))}</b>"
             + ("" if db.flag("fines_enabled") else r.L(" · ⚪ jarimalar o'chiq", " · ⚪ штрафы выключены")),
             r.L("Xodim «Проёб»ga «доброе утро» yozadi. Dam olish kunlari — xodim sozlamalarida.",
                 "Сотрудник пишет «доброе утро» в «Проёб». Выходные — в настройках сотрудника.")]
    rows = [[((r.L("⛔ O'chirish", "⛔ Выключить") if db.flag("attendance_enabled") else r.L("✅ Yoqish", "✅ Включить")),
              "st:t")],
            grid([(r.L("⏰ Eslatma vaqti", "⏰ Напоминание"), "sti:noshow_minutes"),
                  (r.L("💸 Kech qolish jarimasi", "💸 Штраф за опоздание"), "cfi:late_fine")])[0], nav(r, "s")]
    return ui.join(title("🙋", r.L("ISHGA KELISH", "ПРИХОД НА РАБОТУ")), "", card(lines)), kb(*rows)


@screen("sti", "full")
async def num_setting_ask(ctx, r: Req):
    key = r.args[0]
    back = "sr" if key.startswith("break") else "st"
    ui.ask(r, "num_setting", back, key=key)
    prompts = {"noshow_minutes": r.L("Ish boshlanib necha daqiqadan keyin eslatilsin? (masalan 15)",
                                     "Через сколько минут после начала напомнить? (например 15)"),
               "break_minutes": r.L("Tanaffus necha daqiqa?", "Сколько минут перерыв?"),
               "breaks_per_day": r.L("Kuniga necha marta?", "Сколько раз в день?")}
    return title("⚙️", r.L("SOZLAMA", "НАСТРОЙКА")) + "\n\n" + card([prompts[key]]), ui.cancel_kb(r, back)


@on_input("num_setting")
async def num_setting(ctx, r: Req, key: str):
    v = parse_number(r.text)
    limits = {"noshow_minutes": (1, 600), "break_minutes": (5, 240),
              "breaks_per_day": (1, 20)}
    lo, hi = limits[key]
    if v is None or not lo <= v <= hi:
        return r.L(f"⚠️ {lo} dan {hi} gacha", f"⚠️ От {lo} до {hi}")
    ctx.db.set(key, str(int(v)))
    r.args = []
    return await (breaks(ctx, r) if key.startswith("break") else attendance(ctx, r))


@screen("sr", "full")
async def breaks(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] == "t":
        db.toggle("breaks_enabled")
    lines = [f"☕ {r.L('Tanaffus nazorati', 'Контроль перерывов')} — {onoff(r, db.flag('breaks_enabled'))}",
             f"⏱ {r.L('Davomiyligi', 'Длительность')} — <b>{db.get('break_minutes')} {r.L('daq', 'мин')}</b>",
             f"🔁 {r.L('Kuniga', 'В день')} — <b>{db.get('breaks_per_day')}</b>",
             r.L("«атайду» / «перерыв» — boshlash, «тут» — qaytish. Vaqt oshsa — eslatma (jarimasiz). Papkaning hamma "
                 "xodimi tanaffusda bo'lsa, zaderjka hisoblanmaydi.",
                 "«атайду» / «перерыв» — начало, «тут» — возврат. Время вышло — напоминание (без штрафа). Если вся "
                 "папка на перерыве — задержка не считается.")]
    rows = [[((r.L("⛔ O'chirish", "⛔ Выключить") if db.flag("breaks_enabled") else r.L("✅ Yoqish", "✅ Включить")),
              "sr:t")],
            grid([(r.L("⏱ Daqiqa", "⏱ Минуты"), "sti:break_minutes"), (r.L("🔁 Necha marta", "🔁 Сколько раз"),
                                                                        "sti:breaks_per_day")])[0], nav(r, "s")]
    return ui.join(title("☕", r.L("TANAFFUS", "ПЕРЕРЫВЫ")), "", card(lines)), kb(*rows)


# ───────────────────────── kassa ma'lumotini ko'chirish
@screen("sk", "owner")
async def kassa_import(ctx, r: Req):
    db = ctx.db
    ui.ask(r, "import_file", "s")
    lines = [r.L("Faylni shu yerga yuboring (forward ham bo'ladi):", "Пришлите файл сюда (можно переслать):"),
             r.L("• <b>kassa.db</b> — eski kassa boti <code>/export</code> buyrug'i bilan yuboradi;",
                 "• <b>kassa.db</b> — старый бот кассы присылает по команде <code>/export</code>;"),
             r.L("• eski zaderjka botining «💾 Rezerv nusxa» fayli (kerak bo'lsa).",
                 "• файл «💾 Резервная копия» старого бота задержек (если нужно).")]
    for key, uz, ru in (("kassa_imported", "Kassa ko'chirilgan", "Касса перенесена"),
                        ("old_imported", "Eski bot ko'chirilgan", "Старый бот перенесён")):
        if db.get(key):
            lines.append(f"✅ {r.L(uz, ru)}: {h(db.get(key))}")
    lines.append(r.L("Qayta yuborilsa — eski ma'lumot yangisi bilan almashtiriladi.",
                     "Повторная отправка заменит данные."))
    return ui.join(title("📥", r.L("MA'LUMOT KO'CHIRISH", "ПЕРЕНОС ДАННЫХ")), "", card(lines)), ui.cancel_kb(r, "s")


@on_input("import_file", "owner")
async def import_file(ctx, r: Req):
    m = r.message
    doc = getattr(m, "document", None) if m is not None else None
    if doc is None:
        return r.L("⚠️ Fayl yuboring (kassa.db)", "⚠️ Пришлите файл (kassa.db)")
    path = os.path.join(str(ctx.cfg.data_dir), f".import_{int(time.time())}.db")
    try:
        await ctx.bot.download(doc.file_id, destination=path)
    except Exception as exc:
        return r.L(f"⚠️ Yuklab bo'lmadi: {h(exc)}", f"⚠️ Не скачалось: {h(exc)}")
    from .migrate import detect, import_kassa, import_old
    try:
        kind = detect(path)
        if kind == "kassa":
            stats = import_kassa(ctx.db, path)
            what = r.L("Kassa ma'lumoti ko'chirildi", "Данные кассы перенесены")
        elif kind == "old":
            stats = import_old(ctx.db, path, int(ctx.clock()))
            ctx.tracker.reload()
            ctx.userbot.reload_ids()
            ctx.userbot.wake()
            ctx.pool.sync()
            what = r.L("Eski bot ma'lumoti ko'chirildi", "Данные старого бота перенесены")
        elif kind == "new":
            return r.L("⚠️ Bu — shu botning o'z nusxasi, uni ko'chirish shart emas",
                       "⚠️ Это копия этого же бота — переносить не нужно")
        else:
            return r.L("⚠️ Bu fayl tanilmadi (kassa.db kerak)", "⚠️ Файл не распознан (нужен kassa.db)")
    except Exception as exc:
        return r.L(f"⚠️ Fayl o'qilmadi: {h(exc)}", f"⚠️ Файл не прочитан: {h(exc)}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    lines = [f"{h(k)}: <b>{v}</b>" for k, v in stats.items()]
    await ui.toast(ctx.bot, r.chat_id, f"✅ {what}", 6)
    return ui.join(title("📥", r.L("KO'CHIRILDI", "ПЕРЕНЕСЕНО")), "", card(lines), card(
        [r.L("Endi 👥 Xodimlar ro'yxatini tekshiring: bir odam ikki marta chiqsa — ⚙️ → 🔗 Birlashtirish.",
             "Проверьте 👥 Сотрудников: если человек дважды — ⚙️ → 🔗 Объединить.")])), kb(nav(r, "s"))


# ───────────────────────── zaxira nusxa
@screen("sb", "owner")
async def backup(ctx, r: Req):
    from .services import make_backup
    data, name = make_backup(ctx)
    await ctx.notifier.send_document(r.chat_id, data, name, r.L("💾 Baza nusxasi (hamma ma'lumot).",
                                                               "💾 Копия базы (все данные)."))
    return None


# ───────────────────────── chat qidirish
@screen("sx", "full")
async def search_ask(ctx, r: Req):
    ui.ask(r, "search", "s")
    return title("🔎", r.L("CHAT QIDIRISH", "ПОИСК ЧАТА")) + "\n\n" + card(
        [r.L("Chat nomining bir qismini yuboring (<code>*</code> — birinchi 15 ta). ID ni ko'rsataman.",
             "Пришлите часть названия чата (<code>*</code> — первые 15). Покажу ID.")]), ui.cancel_kb(r, "s")


@on_input("search")
async def search(ctx, r: Req):
    try:
        found = await ctx.userbot.search_dialogs("" if r.text.strip() == "*" else r.text)
    except Exception:
        return r.L("⚠️ Asosiy akkaunt ulanmagan", "⚠️ Основной аккаунт не подключён")
    kinds = {"channel": r.L("kanal", "канал"), "group": r.L("guruh", "группа"), "private": r.L("shaxsiy", "личный")}
    lines = [f"• {h(n or '—')} — <code>{i}</code> ({kinds.get(k, k)})" for i, n, k in found] or \
        [r.L("Hech narsa topilmadi.", "Ничего не найдено.")]
    return ui.join(title("🔎", r.L("NATIJA", "РЕЗУЛЬТАТ")), "", card(lines)), \
        kb([(r.L("🔎 Yana qidirish", "🔎 Искать ещё"), "sx")], nav(r, "s"))
