"""⚙️ Sozlamalar: «Проёб» guruhi, akkauntlar (asosiy va Push), adminlar, ishga kelish va tanaffus, kassa
ma'lumotini ko'chirish, zaxira nusxa, chat qidirish, botni to'xtatish."""
from __future__ import annotations

import logging
import os
import re
import time

from . import people as P
from .kassa import zp_mode
from . import ui
from .tgclient import LoginFlow
from .timeutil import fmt, parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title

log = logging.getLogger("settings")

STATE_UZ = {"online": "🟢 ulangan", "connecting": "🟡 ulanmoqda…", "starting": "🟡 ishga tushmoqda…",
            "offline": "🟡 Telegram serveri javob bermayapti — o'zi ulanadi", "unauthorized": "🔑 seans o'chgan",
            "banned": "⛔ akkaunt bloklangan", "no_session": "⚪ ulanmagan", "disabled": "⚪ API_ID / API_HASH yo'q",
            "paused": "⏸ pauzada"}
STATE_RU = {"online": "🟢 подключён", "connecting": "🟡 подключается…", "starting": "🟡 запускается…",
            "offline": "🟡 сервер Telegram не отвечает — подключится сам", "unauthorized": "🔑 сессия завершена",
            "banned": "⛔ аккаунт заблокирован", "no_session": "⚪ не подключён", "disabled": "⚪ нет API_ID / API_HASH",
            "paused": "⏸ на паузе"}
STATE_ICON = {"online": "🟢", "paused": "⏸", "offline": "🟡", "unauthorized": "🔑", "banned": "⛔", "no_session": "⚪"}


def st(r: Req, state: str) -> str:
    return (STATE_RU if r.lang == "ru" else STATE_UZ).get(state, state)


def reason_lines(ctx, r: Req, acc) -> list[str]:
    """Nega ulanmagan va nima qilish kerak — aniq (akkaunt kartasida)."""
    if acc is None:
        return []
    out = []
    if acc.state == "offline":
        out.append(r.L("Hech narsa qilmang — Telegram javob bergach, o'zi ulanadi.",
                       "Ничего не делайте — подключится сам, когда Telegram ответит."))
        if acc.down_since:
            out.append(r.L(f"⏱ {fmt(acc.down_since, ctx.tz, '%H:%M')} dan beri", f"⏱ с {fmt(acc.down_since, ctx.tz, '%H:%M')}")
                       + (r.L(f" · keyingi urinish {fmt(acc.retry_at, ctx.tz, '%H:%M:%S')}",
                              f" · следующая попытка {fmt(acc.retry_at, ctx.tz, '%H:%M:%S')}") if acc.retry_at else ""))
    elif acc.state == "connecting":
        out.append(r.L("Ulanmoqda (45 soniyagacha). Bo'lmasa — o'zi qayta uradi.",
                       "Подключается (до 45 секунд). Не выйдет — попробует снова сам."))
    elif acc.state == "unauthorized":
        out.append(r.L("Akkauntdan chiqilgan yoki seans boshqa qurilmada o'chirilgan. «🔑 Qayta kirish» bosing — "
                       "papkasi va sozlamalari saqlanadi.",
                       "Из аккаунта вышли или сессию завершили на другом устройстве. Нажмите «🔑 Войти заново» — "
                       "папка и настройки сохранятся."))
    elif acc.state == "banned":
        out.append(r.L("Telegram akkauntni bloklagan. Bot unga urinmaydi — boshqa akkaunt ulang.",
                       "Telegram заблокировал аккаунт. Бот не пытается — подключите другой аккаунт."))
    if acc.error and acc.state != "online":
        out.append(f"<i>{h(acc.error)}</i>")
    return out


@screen("s", "full")
async def settings(ctx, r: Req):
    db = ctx.db
    ub = ctx.userbot
    accs = db.all("SELECT * FROM accounts ORDER BY id")
    lines = [f"⏯ {r.L('Bot', 'Бот')} — {onoff(r, db.flag('bot_enabled'))}",
             f"🔑 {r.L('Asosiy akkaunt', 'Основной аккаунт')} — {st(r, ub.state if ub else 'disabled')}"
             + (f" · {h(ub.me_label)}" if ub and ub.me_label else ""),
             f"📲 {r.L('Push akkauntlar', 'Пуш-аккаунты')} — <b>{len(accs)}</b>",
             "👥 «Проёб» — " + (f"<code>{h(db.get('proyob_group_id'))}</code>" if db.get("proyob_group_id")
                                else r.L("belgilanmagan ⚠️", "не задана ⚠️")),
             f"✍️ {r.L('«Проёб»ga yozadi', 'Пишет в «Проёб»')} — " + (r.L("🔑 asosiy akkaunt", "🔑 основной аккаунт")
                                                                    if db.get("proyob_sender") == "main"
                                                                    else r.L("🤖 bot", "🤖 бот")),
             f"💸 {r.L('Avto-jarimalar', 'Авто-штрафы')} — {onoff(r, db.flag('fines_enabled'))}",
             f"🧮 {r.L('Zp hisoblash', 'Расчёт зп')} — " + {"button": r.L("tugma bilan", "по кнопке"),
                                                           "auto": r.L("avtomatik", "автоматически"),
                                                           "off": r.L("o'chiq", "выключен")}[zp_mode(db)],
             f"🙋 {r.L('Ishga kelish', 'Приход')} — {onoff(r, db.flag('attendance_enabled'))} · "
             f"☕ {r.L('Tanaffus', 'Перерывы')} — {onoff(r, db.flag('breaks_enabled'))}"]
    btn = [(r.L("👥 «Проёб» guruhi", "👥 Группа «Проёб»"), "sg"), (r.L("🔑 Asosiy akkaunt", "🔑 Основной аккаунт"), "sm"),
           (r.L("📲 Push akkauntlar", "📲 Пуш-аккаунты"), "sa"), (r.L("👮 Adminlar", "👮 Админы"), "sd"),
           (r.L("🙋 Ishga kelish", "🙋 Приход"), "st"), (r.L("☕ Tanaffus", "☕ Перерывы"), "sr"),
           (r.L("📥 Ko'chirish", "📥 Перенос данных"), "sk"), (r.L("💾 Zaxira nusxa", "💾 Резервная копия"), "sb"),
           (r.L("🔎 Chat qidirish", "🔎 Поиск чата"), "sx")]
    if r.owner:
        btn.append((r.L("🧮 Zp hisoblash", "🧮 Расчёт зп"), "kzm"))
        btn.append((r.L("🧹 Tozalash", "🧹 Очистка"), "sz"))
        btn.append((r.L("🧩 Qo'shimcha funksiyalar", "🧩 Доп. функции"), "ans"))
        btn.append((r.L("✍️ «Проёб»ga kim yozadi", "✍️ Кто пишет в «Проёб»"), "sgw"))
    rows = grid(btn)
    rows.append([((r.L("💸 Jarimalarni o'chirish", "💸 Выключить штрафы") if db.flag("fines_enabled") else
                   r.L("💸 Jarimalarni yoqish", "💸 Включить штрафы")), "sfn")])
    rows.append([((r.L("⛔ Botni to'xtatish", "⛔ Остановить бота") if db.flag("bot_enabled") else
                   r.L("▶️ Botni yoqish", "▶️ Включить бота")), "so")])
    rows.append(nav(r))
    from datetime import datetime
    started = datetime.fromtimestamp(ctx.started, ctx.tz)
    lines.append(f"🖥 {r.L('Server', 'Сервер')} — <code>{h(server_name())}</code> · "
                 f"{r.L('ishga tushgan', 'запущен')} {started:%d.%m %H:%M}")
    return ui.join(title("⚙️", r.L("SOZLAMALAR", "НАСТРОЙКИ")), "", card(lines)), kb(*rows)


def server_name() -> str:
    """Qaysi nusxa javob beryapti (Railway servisi). Ikki xil chiqsa — bot ikki joyda ishlayapti."""
    import socket
    name = os.environ.get("RAILWAY_SERVICE_NAME") or "bot"
    rid = os.environ.get("RAILWAY_REPLICA_ID") or os.environ.get("RAILWAY_DEPLOYMENT_ID") or socket.gethostname()
    return f"{name} · {rid[:6]}"


WIPE = {"kassa": ("🧾", "Kassa yozuvlari", "Записи кассы",
                  "cheklar, hisobotlar, jarima/bonus/avans, to'lovlar, ulushlar, haftalik foizlar, tarix",
                  "чеки, отчёты, штрафы/бонусы/авансы, выплаты, доли, недельные проценты, история"),
        "people": ("👥", "Xodimlar (kassa ham)", "Сотрудники (и касса)",
                   "hamma xodimlar, foizlari, papkadagi o'rni, ishga kelish — va hamma kassa yozuvlari",
                   "все сотрудники, проценты, места в папках, приход — и все записи кассы"),
        "push": ("📲", "Push akkauntlar", "Пуш-аккаунты", "Push akkauntlar (qayta kirasiz)",
                 "Пуш-аккаунты (войдёте заново)"),
        "all": ("🧹", "Hammasi", "Всё", "kassa, xodimlar va Push akkauntlar", "касса, сотрудники и Пуш-аккаунты")}


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
              f"📲 {r.L('Push', 'Пуш')} — <b>{db.scalar('SELECT COUNT(*) FROM accounts')}</b>"]
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


@screen("sgw", "owner")
async def group_sender(ctx, r: Req):
    """«Проёб»ga kim nomidan yoziladi: bot yoki asosiy akkaunt (u guruhda anonim admin bo'lsa — «Проёб» nomidan)."""
    db = ctx.db
    if r.args and r.args[0] in ("bot", "main"):
        db.set("proyob_sender", r.args[0])
    cur = db.get("proyob_sender")
    ub = ctx.userbot
    ok = ub is not None and ub.state == "online"
    lines = [f"{r.L('Hozir', 'Сейчас')}: <b>" + (r.L("🔑 asosiy akkaunt", "🔑 основной аккаунт") if cur == "main"
                                                   else r.L("🤖 bot", "🤖 бот")) + "</b>",
             "",
             r.L("<b>🔑 Asosiy akkaunt</b> — xabarlar asosiy akkauntingiz nomidan chiqadi. Uni «Проёб»da "
                 "<b>anonim admin</b> qilsangiz (guruh → ✏️ → Administratorlar → akkaunt → «anonim qolish») — "
                 "«Проёб» nomidan chiqadi.",
                 "<b>🔑 Основной аккаунт</b> — сообщения от имени вашего основного аккаунта. Сделайте его в «Проёб» "
                 "<b>анонимным админом</b> (Изменить → Администраторы → аккаунт → «Оставаться анонимным») — "
                 "будут от имени «Проёб»."),
             r.L("Kamchiligi: oddiy akkaunt tugma qo'sha olmaydi — «✅ Выполнено» tugmasi bo'lmaydi (zaderjka xodim "
                 "lidga javob berganda o'zi yopiladi). Tugmali savollar (kassa) bot nomidan qoladi.",
                 "Минус: обычный аккаунт не может добавить кнопку — «✅ Выполнено» не будет (задержка закрывается сама, "
                 "когда сотрудник ответил лиду). Вопросы с кнопками (касса) остаются от бота."),
             r.L("Asosiy akkaunt uzilib qolsa — xabar yo'qolmaydi, bot o'zi yozadi.",
                 "Если основной аккаунт отключится — сообщение не пропадёт, напишет бот.")]
    if cur == "main" and not ok:
        lines.append(r.L("⚠️ Asosiy akkaunt hozir ulanmagan — bot yozyapti.", "⚠️ Основной аккаунт не подключён — пишет бот."))
    rows = [[(("✅ " if cur != "main" else "") + r.L("🤖 Bot", "🤖 Бот"), "sgw:bot"),
             (("✅ " if cur == "main" else "") + r.L("🔑 Asosiy akkaunt", "🔑 Основной аккаунт"), "sgw:main")],
            nav(r, "s")]
    return ui.join(title("✍️", r.L("«ПРОЁБ»GA KIM YOZADI", "КТО ПИШЕТ В «ПРОЁБ»")), "", card(lines)), kb(*rows)


# ───────────────────────── asosiy akkaunt va login
@screen("sm", "full")
async def main_account(ctx, r: Req):
    ub = ctx.userbot
    lines = [f"{r.L('Holati', 'Состояние')} — {st(r, ub.state)}"] + reason_lines(ctx, r, ub)
    if ub.me_label:
        lines.append(f"👤 {h(ub.me_label)}")
    if ub.last_sync:
        lines.append(r.L("Oxirgi sinxron: ", "Последняя синхронизация: ") + time.strftime(
            "%H:%M", time.localtime(ub.last_sync)))
    lines.append(r.L("Asosiy akkaunt ish chatlarini kuzatadi (faqat kim/qachon). Push yubormaydi.",
                     "Основной аккаунт следит за чатами (только кто/когда). Пуш не шлёт."))
    rows = [[((r.L("🔑 Qayta kirish", "🔑 Войти заново") if ub.state == "unauthorized" else
               r.L("📲 Ulash / almashtirish", "📲 Подключить / сменить")), "sml:main")],
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


LOGIN_TTL = 15 * 60                                       # kod shu vaqtgacha amal qiladi


def _login_key(uid: int) -> str:
    return f"login:{uid}"


def _login_save(ctx, uid: int, flow, target: str) -> None:
    """Kirish jarayoni bazada ham: bot yangilanib qayta ishga tushsa, kod baribir qabul qilinadi."""
    import json
    st = dict(flow.state(), target=target, ts=int(time.time()))
    ui.quiet_store(lambda: ctx.db.set(_login_key(uid), json.dumps(st)))


def _login_forget(ctx, uid: int) -> None:
    def go():
        ctx.db.run("DELETE FROM settings WHERE key=?", (_login_key(uid),))
        ctx.db._cache.pop(_login_key(uid), None)
    ui.quiet_store(go)


async def _login_flow(ctx, uid: int):
    """Xotirada bo'lmasa — bazadan tiklanadi (bot qayta ishga tushgan bo'lsa)."""
    import json
    flow = ctx.login.get(uid)
    if flow is not None:
        return flow
    raw = ctx.db.get(_login_key(uid))
    if not raw:
        return None
    try:
        st = json.loads(raw)
    except ValueError:
        return None
    if time.time() - st.get("ts", 0) > LOGIN_TTL or not st.get("s"):
        _login_forget(ctx, uid)
        return None
    flow = await LoginFlow.resume(ctx.cfg.api_id, ctx.cfg.api_hash, st)
    ctx.login[uid] = flow
    return flow


def login_error(r: Req, exc: Exception, stage: str) -> str:
    """Telegram xatosi — tushunarli so'z bilan."""
    name = type(exc).__name__
    sec = getattr(exc, "seconds", None)
    known = {
        "PhoneNumberInvalidError": r.L("Raqam noto'g'ri. Masalan: +998901234567", "Неверный номер. Пример: +998901234567"),
        "PhoneNumberBannedError": r.L("Bu raqam Telegram'da bloklangan", "Этот номер заблокирован в Telegram"),
        "PhoneCodeInvalidError": r.L("Kod noto'g'ri. Qaytadan yozing", "Неверный код. Напишите ещё раз"),
        "PhoneCodeEmptyError": r.L("Kod yozilmadi", "Код не указан"),
        "PhoneCodeExpiredError": r.L("Kod eskirdi. «🔄 Yangi kod» ni bosing", "Код устарел. Нажмите «🔄 Новый код»"),
        "PasswordHashInvalidError": r.L("Parol noto'g'ri. Qaytadan yozing", "Неверный пароль. Напишите ещё раз"),
        "ApiIdInvalidError": r.L("Railway'dagi API_ID / API_HASH noto'g'ri", "Неверные API_ID / API_HASH в Railway"),
        "FloodWaitError": r.L(f"Telegram kutishni so'radi: {(sec or 60) // 60 + 1} daqiqa",
                              f"Telegram просит подождать: {(sec or 60) // 60 + 1} мин"),
    }
    msg = known.get(name) or (r.L("Kod yuborilmadi", "Код не отправлен") if stage == "phone" else
                              r.L("Kirib bo'lmadi", "Не удалось войти")) + f" ({h(name)})"
    return "⚠️ " + msg


def _back(target: str) -> str:
    """Bekor qilinsa — qayerga: papkadan boshlangan bo'lsa o'sha papkaga, qayta kirish — akkaunt kartasiga."""
    if target.startswith("push:"):
        return f"uf:{target.split(':', 1)[1]}"
    if target.startswith("re:"):
        return f"sa:{target.split(':', 1)[1]}"
    return "s"


def _phone_screen(r: Req, target: str, err: str = ""):
    if target == "main":
        what = r.L("asosiy akkaunt", "основной аккаунт")
    elif target.startswith("re:"):
        what = r.L("qayta kirish — o'sha akkaunt raqami", "вход заново — номер того же аккаунта")
    else:
        what = r.L("yangi Push akkaunt", "новый Пуш-аккаунт")
    return title("📲", r.L("ULASH", "ПОДКЛЮЧЕНИЕ"), what) + "\n\n" + card(
        ([err, ""] if err else []) +
        [r.L("Telefon raqamini yuboring, masalan <code>+998901234567</code>.",
             "Пришлите номер телефона, например <code>+998901234567</code>.")]), ui.cancel_kb(r, _back(target))


def _code_screen(r: Req, phone: str, err: str = ""):
    return title("🔐", r.L("KOD", "КОД"), h(phone)) + "\n\n" + card(
        ([err, ""] if err else []) +
        [r.L("Telegram yuborgan kodni <b>bo'shliq bilan</b> yozing: <code>1 2 3 4 5</code>",
             "Напишите код из Telegram <b>через пробелы</b>: <code>1 2 3 4 5</code>"),
         r.L("<i>Kodni bo'shliqsiz yozsangiz yoki forward qilsangiz, Telegram uni bekor qiladi.</i>",
             "<i>Если написать код без пробелов или переслать — Telegram его отменит.</i>")]), \
        kb([(r.L("🔄 Yangi kod", "🔄 Новый код"), "smr")], [(r.L("✖️ Bekor qilish", "✖️ Отмена"), "smx")])


def _pass_screen(r: Req, err: str = ""):
    return title("🔐", r.L("PAROL", "ПАРОЛЬ")) + "\n\n" + card(
        ([err, ""] if err else []) +
        [r.L("Ikki bosqichli parolni yuboring (xabar darhol o'chiriladi).",
             "Пришлите пароль двухэтапной проверки (сообщение сразу удалится).")]), \
        kb([(r.L("✖️ Bekor qilish", "✖️ Отмена"), "smx")])


@screen("sml", "full")
async def login_start(ctx, r: Req):
    target = r.args[0] if r.args else "main"
    if target == "push" and len(r.args) > 1 and r.args[1].isdigit():
        target = f"push:{r.args[1]}"                   # 📣 Push → papka → akkaunt: ulangach shu papkaga biriktiriladi
    elif target == "re" and len(r.args) > 1 and r.args[1].isdigit():
        target = f"re:{r.args[1]}"                     # 🔑 qayta kirish: o'sha akkaunt yozuvi (papkasi saqlanadi)
    if not (ctx.cfg.api_id and ctx.cfg.api_hash):
        return r.L("⚠️ Railway'da API_ID va API_HASH berilmagan", "⚠️ В Railway не заданы API_ID и API_HASH")
    ui.ask(r, "login_phone", _back(target), target=target)
    return _phone_screen(r, target)


@on_input("login_phone")
async def login_phone(ctx, r: Req, target: str):
    contact = getattr(r.message, "contact", None)          # «📎 → Kontakt» bilan yuborilgan raqam ham bo'ladi
    phone = re.sub(r"[^\d+]", "", r.text or (getattr(contact, "phone_number", "") or ""))
    if len(re.sub(r"\D", "", phone)) < 9:
        ui.ask(r, "login_phone", _back(target), target=target)
        return _phone_screen(r, target, r.L("⚠️ Raqam noto'g'ri", "⚠️ Неверный номер"))
    if not phone.startswith("+"):
        phone = "+" + phone
    old = ctx.login.pop(r.uid, None)
    if old is not None:
        await old.cancel()
    flow = LoginFlow(ctx.cfg.api_id, ctx.cfg.api_hash)
    try:
        await flow.start(phone)
    except Exception as exc:
        await flow.cancel()
        ui.ask(r, "login_phone", _back(target), target=target)
        return _phone_screen(r, target, login_error(r, exc, "phone"))
    ctx.login[r.uid] = flow
    _login_save(ctx, r.uid, flow, target)
    ui.ask(r, "login_code", _back(target), target=target)
    return _code_screen(r, phone)


@screen("smr", "full")
async def login_resend(ctx, r: Req):
    """🔄 Yangi kod — o'sha raqamga qaytadan."""
    import json
    raw = ctx.db.get(_login_key(r.uid))
    st = json.loads(raw) if raw else {}
    phone, target = st.get("phone") or "", st.get("target") or "main"
    if not phone:
        ui.ask(r, "login_phone", _back(target), target=target)
        return _phone_screen(r, target)
    old = ctx.login.pop(r.uid, None)
    if old is not None:
        await old.cancel()
    flow = LoginFlow(ctx.cfg.api_id, ctx.cfg.api_hash)
    try:
        await flow.start(phone)
    except Exception as exc:
        await flow.cancel()
        ui.ask(r, "login_code", _back(target), target=target)
        return _code_screen(r, phone, login_error(r, exc, "phone"))
    ctx.login[r.uid] = flow
    _login_save(ctx, r.uid, flow, target)
    ui.ask(r, "login_code", _back(target), target=target)
    return _code_screen(r, phone, r.L("📨 Yangi kod yuborildi", "📨 Новый код отправлен"))


@screen("smx", "full")
async def login_cancel(ctx, r: Req):
    import json
    flow = ctx.login.pop(r.uid, None)
    if flow is not None:
        await flow.cancel()
    raw = ctx.db.get(_login_key(r.uid))
    target = (json.loads(raw).get("target") or "") if raw else ""
    _login_forget(ctx, r.uid)
    ui.WAIT.pop(r.uid, None)
    if target.startswith("push:"):
        from .panel_push import folder_card
        r.args = [target.split(":", 1)[1]]
        ui.view(r, f"uf:{r.args[0]}")
        return await folder_card(ctx, r)
    if target.startswith("re:"):
        r.args = [target.split(":", 1)[1]]
        return await accounts(ctx, r)
    return await settings(ctx, r)


@on_input("login_code")
async def login_code(ctx, r: Req, target: str):
    try:
        flow = await _login_flow(ctx, r.uid)
    except Exception as exc:
        flow = None
        log.warning("Kirishni tiklab bo'lmadi: %s", type(exc).__name__)
    if flow is None:
        _login_forget(ctx, r.uid)
        ui.ask(r, "login_phone", _back(target), target=target)
        return _phone_screen(r, target, r.L("⚠️ Kod eskirdi — raqamni qaytadan yuboring",
                                            "⚠️ Код устарел — пришлите номер ещё раз"))
    code = re.sub(r"\D", "", r.text)
    try:
        res = await flow.submit_code(code)
    except Exception as exc:
        ui.ask(r, "login_code", _back(target), target=target)
        return _code_screen(r, flow.phone, login_error(r, exc, "code"))
    if res == "password":
        _login_save(ctx, r.uid, flow, target)
        ui.ask(r, "login_pass", _back(target), target=target)
        return _pass_screen(r)
    return await login_done(ctx, r, target)


@on_input("login_pass")
async def login_pass(ctx, r: Req, target: str):
    try:
        flow = await _login_flow(ctx, r.uid)
    except Exception:
        flow = None
    if flow is None:
        _login_forget(ctx, r.uid)
        ui.ask(r, "login_phone", _back(target), target=target)
        return _phone_screen(r, target, r.L("⚠️ Vaqt o'tib ketdi — raqamni qaytadan yuboring",
                                            "⚠️ Время вышло — пришлите номер ещё раз"))
    try:
        await flow.submit_password(r.text)
    except Exception as exc:
        ui.ask(r, "login_pass", _back(target), target=target)
        return _pass_screen(r, login_error(r, exc, "pass"))
    return await login_done(ctx, r, target)


async def login_done(ctx, r: Req, target: str):
    flow = ctx.login.pop(r.uid)
    session = flow.session_string()
    await flow.cancel()
    _login_forget(ctx, r.uid)
    if target == "main":
        await ctx.userbot.set_session(session)
        await ui.toast(ctx.bot, r.chat_id, r.L("✅ Asosiy akkaunt ulandi", "✅ Основной аккаунт подключён"))
        return await main_account(ctx, r)
    if target.startswith("re:"):
        aid = int(target.split(":", 1)[1])
        if ctx.db.one("SELECT 1 FROM accounts WHERE id=?", (aid,)) is not None:
            ctx.pool.relogin(aid, session)
            await ctx.notifier.resolve(f"unauth-push-{aid}")
            await ui.toast(ctx.bot, r.chat_id, r.L("✅ Qayta kirildi — papkasi joyida", "✅ Вход выполнен — папка на месте"))
            r.args = [str(aid)]
            return await accounts(ctx, r)
    n = ctx.db.scalar("SELECT COUNT(*) FROM accounts") + 1
    aid = ctx.db.run("INSERT INTO accounts(name, session, added_ts) VALUES(?,?,?)",
                     (f"Push {n}", session, int(time.time()))).lastrowid
    ctx.pool.sync()
    await ui.toast(ctx.bot, r.chat_id, r.L("✅ Push akkaunt qo'shildi", "✅ Пуш-аккаунт добавлен"))
    fid = int(target.split(":", 1)[1]) if target.startswith("push:") else 0
    if fid and P.folder(ctx.db, fid) is not None:
        P.set_folder(ctx.db, fid, push_account_id=int(aid))
        from .panel_push import folder_card
        r.args = [str(fid)]
        ui.view(r, f"uf:{fid}")
        return await folder_card(ctx, r)
    return await accounts(ctx, r)


# ───────────────────────── Push akkauntlar
def spam_line(ctx, r: Req, spam: str, ts) -> str:
    """🛡 @SpamBot tekshiruvi natijasi (kuniga bir marta)."""
    when = f" · {fmt(ts, ctx.tz)}" if ts else ""
    if not ctx.db.flag("spam_check"):
        return r.L("🛡 Spam tekshiruvi — ⚪ o'chiq", "🛡 Проверка спама — ⚪ выкл")
    if spam == "limited":
        return r.L(f"🛡 Spam — 🚫 cheklov bor, Push to'xtatilgan{when}", f"🛡 Спам — 🚫 ограничение, Пуш остановлен{when}")
    if spam == "ok":
        return r.L(f"🛡 Spam — ✅ cheklov yo'q{when}", f"🛡 Спам — ✅ ограничений нет{when}")
    return r.L("🛡 Spam — hali tekshirilmagan (har kuni 09:00 dan keyin)",
               "🛡 Спам — ещё не проверялся (каждый день после 09:00)")


@screen("sa", "full")
async def accounts(ctx, r: Req):
    db = ctx.db
    if r.args:
        return await account_card(ctx, r)
    rows = []
    for a in db.all("SELECT * FROM accounts ORDER BY id"):
        state = ctx.pool.state_of(a["id"]) if ctx.pool else "no_session"
        icon = STATE_ICON.get(state, "🟡")
        if a["spam"] == "limited":
            icon = "🚫"
        rows.append([(f"{icon} {a['name']} {a['label']}"[:50], f"sa:{a['id']}")])
    rows.append([(r.L("➕ Push akkaunt qo'shish", "➕ Добавить Пуш-аккаунт"), "sml:push")])
    rows.append(nav(r, "s"))
    return ui.join(title("📲", r.L("PUSH AKKAUNTLAR", "ПУШ-АККАУНТЫ")), "", card(
        [r.L("Har papkaga o'z akkaunti (📣 Push → 📁 Papkalar). Akkaunt kerakli chatlarda bo'lishi kerak.",
             "У каждой папки свой аккаунт (📣 Пуш → 📁 Папки). Аккаунт должен быть в нужных чатах.")])), kb(*rows)


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
    state = ctx.pool.state_of(aid)
    acc = ctx.pool.account(aid) if not a["paused"] else None
    lines = [f"{r.L('Holati', 'Состояние')} — {st(r, state)}"] + reason_lines(ctx, r, acc) + \
        [f"👤 {h(a['label'] or '—')}", f"📁 {h(', '.join(used) or r.L('papka yo‘q', 'нет папок'))}",
         spam_line(ctx, r, a["spam"], a["spam_ts"])]
    rows = []
    if state in ("unauthorized", "no_session") or (acc is not None and acc.state == "banned"):
        rows.append([(r.L("🔑 Qayta kirish", "🔑 Войти заново"), f"sml:re:{aid}")])
    rows += grid([((r.L("▶️ Davom ettirish", "▶️ Возобновить") if a["paused"] else r.L("⏸ Pauza", "⏸ Пауза")),
                   f"sa:{aid}:p"), (r.L("✏️ Nomi", "✏️ Название"), f"sa:{aid}:n"),
                  (r.L("🔑 Qayta kirish", "🔑 Войти заново"), f"sml:re:{aid}") if state == "online" else None,
                  (r.L("🗑 O'chirish", "🗑 Удалить"), f"sa:{aid}:x")])
    rows = [[b for b in row if b] for row in rows]
    rows.append(nav(r, "sa"))
    return ui.join(title("📲", h(a["name"])), "", card(lines)), kb(*rows)


@on_input("acc_name")
async def account_rename(ctx, r: Req, aid: int):
    name = r.text.strip()[:30]
    if not name:
        return r.L("⚠️ Nom kerak", "⚠️ Нужно название")
    ctx.db.run("UPDATE accounts SET name=? WHERE id=?", (name, aid))
    r.args = [str(aid)]
    return await accounts(ctx, r)


# ───────────────────────── adminlar
LEVEL_UZ = {"owner": "👑 ega", "full": "🛠 to'liq", "view": "👁 faqat ko'radi", "zp": "💵 faqat zp"}
LEVEL_RU = {"owner": "👑 владелец", "full": "🛠 полный", "view": "👁 только просмотр", "zp": "💵 только зп"}


@screen("sd", "full")
async def admins(ctx, r: Req):
    db = ctx.db
    names = LEVEL_RU if r.lang == "ru" else LEVEL_UZ
    a = r.args
    if a and a[0] == "l" and r.owner:                     # darajani almashtirish
        uid = int(a[1])
        row = db.one("SELECT * FROM admins WHERE user_id=?", (uid,))
        if row:
            order = ["zp", "view", "full", "owner"]
            cur = row["level"] if row["level"] in order else "view"
            P.set_admin(db, uid, order[(order.index(cur) + 1) % len(order)])
        ui.view(r, "sd")
    if a and a[0] == "x" and r.owner:
        P.del_admin(db, int(a[1]))
        ui.view(r, "sd")
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
        rows.append([(r.L("🔐 Tiklash kodi", "🔐 Код восстановления"), "sdr"),
                     (r.L("🔒 Qulf kodi", "🔒 Код блокировки"), "lkc")])
        ts = db.get("recovery_ts")
        lines.append("")
        lines.append(f"🔐 {r.L('Tiklash kodi', 'Код восстановления')} — " +
                     (r.L(f"o'rnatilgan ({time.strftime('%d.%m.%Y', time.localtime(int(ts)))})",
                          f"задан ({time.strftime('%d.%m.%Y', time.localtime(int(ts)))})")
                      if recovery.is_set(db) and ts else r.L("yo'q ⚠️", "нет ⚠️")))
        from . import lock
        lines.append(f"🔒 {r.L('Qulf kodi', 'Код блокировки')} — " +
                     (r.L("o'rnatilgan", "задан") if lock.is_set(db) else r.L("yo'q", "нет")))
    rows.append(nav(r, "s"))
    return ui.join(title("👮", r.L("ADMINLAR", "АДМИНЫ")), "", card(lines), card(
        [r.L("👑 ega — hammasi (ulushingiz ham) · 🛠 to'liq — boshqaruv, ulushingizni ko'rmaydi · 👁 — faqat ko'radi · "
             "💵 faqat zp — jami kassa va zp, har xodimning kassasi, $ va zp si (foizlarsiz, PDF siz, o'zgartira olmaydi, "
             "sizning va Artur ulushi ko'rinmaydi). Bosing — darajani almashtirish.",
             "👑 владелец — всё (и ваша доля) · 🛠 полный — управление, без вашей доли · 👁 — только просмотр · "
             "💵 только зп — общая касса и зп, касса, $ и зп каждого (без процентов и PDF, без изменений, без вашей "
             "доли и доли Артура). Нажмите — сменить уровень.")])), kb(*rows)


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
    from . import fines
    db = ctx.db
    if r.args and r.args[0] == "t":
        db.toggle("attendance_enabled")
        ui.view(r, "st")
    tbl = fines.late_table(db)                             # 🕘 necha daqiqa kech — necha $
    late = db.get_int("late_after_min", 15)
    lines = [f"🙋 {r.L('Nazorat', 'Контроль')} — {onoff(r, db.flag('attendance_enabled'))}",
             f"🕘 {r.L('Ish boshlanishi', 'Начало работы')} — <b>{db.get('work_start')}</b>",
             f"⏰ {r.L('Eslatma', 'Напоминание')} — {r.L('boshlanib', 'через')} <b>{db.get('noshow_minutes')}</b> "
             f"{r.L('daqiqa o‘tsa', 'мин после начала')}",
             f"💸 {r.L('Kech qolish', 'Опоздание')} — {r.L(f'{late}+ daq', f'{late}+ мин')} · "
             f"<b>{fines.late_table_text(tbl, r.lang)}</b>"
             + ("" if db.flag("fines_enabled") else r.L(" · ⚪ jarimalar o'chiq", " · ⚪ штрафы выключены")),
             r.L("Ishga keldi = «Проёб»ga birinchi xabari (kechki kassa hisobotidan tashqari) yoki lidga birinchi "
                 "yozuvi. Kim ishlaydi — 📅 Bugun kim qayerda; dam olish kunlari — xodim sozlamalarida.",
                 "Пришёл = первое сообщение в «Проёб» (кроме вечернего отчёта кассы) или первое сообщение лиду. Кто "
                 "работает — 📅 Кто где сегодня; выходные — в настройках сотрудника.")]
    rows = [[((r.L("⛔ O'chirish", "⛔ Выключить") if db.flag("attendance_enabled") else r.L("✅ Yoqish", "✅ Включить")),
              "st:t")],
            grid([(r.L("⏰ Eslatma vaqti", "⏰ Напоминание"), "sti:noshow_minutes"),
                  (r.L("💸 Kech qolish", "💸 Опоздание"), "cfl")])[0],
            [(r.L("📅 Bugun kim qayerda", "📅 Кто где сегодня"), "rt")], nav(r, "s")]
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
        ui.view(r, "sr")
    if len(r.args) == 2 and r.args[0] == "u" and r.args[1].isdigit() and int(r.args[1]) in SPEEDUP_CHOICES:
        db.set("speedup_min", r.args[1])                  # ⚡ tanaffusdan qaytgach — «ускорьтесь»
        ui.view(r, "sr")
    sp = db.get_int("speedup_min", 8)
    extra_b = db.get("break_words").strip()
    extra_k = db.get("back_words").strip()
    lines = [f"☕ {r.L('Tanaffus nazorati', 'Контроль перерывов')} — {onoff(r, db.flag('breaks_enabled'))}",
             f"⏱ {r.L('Davomiyligi', 'Длительность')} — <b>{db.get('break_minutes')} {r.L('daq', 'мин')}</b>",
             f"🔁 {r.L('Kuniga', 'В день')} — <b>{db.get('breaks_per_day')}</b>",
             "",
             r.L("<b>Boshlash</b> — bot o'zi taniydi: отойду / отойди / атайду / otaydu / ataydim / перерыв / tanaffus / "
                 "obedga / perekur / namozga … (har xil yozilsa ham). Bot javob beradi: «☕ @xodim — перерыв до 14:30».",
                 "<b>Начало</b> — бот узнаёт сам: отойду / отойди / атайду / otaydu / ataydim / перерыв / tanaffus / "
                 "obedga / perekur / namozga … (как бы ни написали). Бот отвечает: «☕ @сотрудник — перерыв до 14:30»."),
             r.L("<b>Qaytish</b> — «тут» / «keldim» / «qaytdim» — istalgan payt. Tanaffus vaqtida lidga yozsa — tanaffus "
                 "davom etadi; vaqti tugagach lidga yoki «Проёб»ga yozsa — qaytdi. Vaqt tugab jim bo'lsa — eslatma.",
                 "<b>Возврат</b> — «тут» / «keldim» / «вернулся» — в любой момент. Пишет лиду во время перерыва — перерыв "
                 "продолжается; после окончания написал лиду или в «Проёб» — вернулся. Время вышло, а он молчит — "
                 "напоминание."),
             r.L("Papkaning bugungi xodimi tanaffusda bo'lsa — zaderjka hisoblanmaydi: «задержка», eslatma va jarima "
                 "chiqmaydi (vaqt to'xtab turadi).",
                 "Если сегодняшний сотрудник папки на перерыве — задержка не считается: «задержка», напоминание и "
                 "штраф не приходят (время стоит)."),
             (r.L(f"⚡ Qaytgach <b>{sp} daqiqa</b> beriladi. Shunda ham tanaffusda kutgan chatlar javobsiz bo'lsa — "
                  "«Проёб»da «⚡ @xodim, ускорьтесь — 2 чата ждут ответа» (jarimasiz). Tanaffusdan oldin chiqqan "
                  "«задержка»ning eslatmasi ham shu vaqtgacha suriladi.",
                  f"⚡ После возврата даётся <b>{sp} мин</b>. Если чаты, ждавшие во время перерыва, всё ещё без ответа — "
                  "в «Проёб»: «⚡ @сотрудник, ускорьтесь — 2 чата ждут ответа» (без штрафа). Напоминание по «задержке» "
                  "до перерыва тоже сдвигается на это время.") if sp else
              r.L("⚡ Qaytgach «ускорьтесь» — o'chiq.", "⚡ «Ускорьтесь» после перерыва — выкл.")),
             "",
             f"➕ {r.L('Qo‘shimcha boshlash so‘zlari', 'Доп. слова начала')}: <b>{h(extra_b) or '—'}</b>",
             f"➕ {r.L('Qo‘shimcha qaytish so‘zlari', 'Доп. слова возврата')}: <b>{h(extra_k) or '—'}</b>"]
    rows = [[((r.L("⛔ O'chirish", "⛔ Выключить") if db.flag("breaks_enabled") else r.L("✅ Yoqish", "✅ Включить")),
              "sr:t")],
            grid([(r.L("⏱ Daqiqa", "⏱ Минуты"), "sti:break_minutes"), (r.L("🔁 Necha marta", "🔁 Сколько раз"),
                                                                        "sti:breaks_per_day")])[0],
            [(r.L("➕ Boshlash so'zlari", "➕ Слова начала"), "srw:break_words"),
             (r.L("➕ Qaytish so'zlari", "➕ Слова возврата"), "srw:back_words")]]
    rows += grid([(("✅ " if sp == v else "") + (f"⚡ {v} {r.L('daq', 'мин')}" if v else r.L("⚡ o'chiq", "⚡ выкл")),
                   f"sr:u:{v}") for v in SPEEDUP_CHOICES], 3)
    rows.append(nav(r, "s"))
    return ui.join(title("☕", r.L("TANAFFUS", "ПЕРЕРЫВЫ")), "", card(lines)), kb(*rows)


SPEEDUP_CHOICES = (0, 5, 6, 8, 10, 15)


@screen("srw", "full")
async def break_words_ask(ctx, r: Req):
    key = r.args[0] if r.args and r.args[0] in ("break_words", "back_words") else "break_words"
    ui.ask(r, "break_words", "sr", key=key)
    what = (r.L("tanaffus boshlanishi", "начала перерыва") if key == "break_words" else
            r.L("tanaffusdan qaytish", "возврата с перерыва"))
    return title("➕", r.L("SO'ZLAR", "СЛОВА"), what) + "\n\n" + card(
        [r.L(f"Hozir: <code>{h(ctx.db.get(key)) or '—'}</code>", f"Сейчас: <code>{h(ctx.db.get(key)) or '—'}</code>"),
         r.L("Xodimlar yozadigan so'zlarni vergul bilan yuboring, masalan <code>chiqib kelaman, 5 minutga</code>. "
             "Bot so'z boshi bo'yicha taniydi (kirill/lotin farqi yo'q). <code>-</code> — tozalash.",
             "Пришлите слова через запятую, например <code>выйду, 5 минут</code>. Бот узнаёт по началу слова "
             "(кириллица/латиница не важны). <code>-</code> — очистить.")]), ui.cancel_kb(r, "sr")


@on_input("break_words")
async def break_words_set(ctx, r: Req, key: str):
    text = (r.text or "").strip()
    if text in ("-", "—"):
        text = ""
    words = [w.strip() for w in re.split(r"[,;\n]+", text) if w.strip()]
    if any(len(w) < 3 for w in words):
        return r.L("⚠️ Har so'z kamida 3 harf", "⚠️ Каждое слово — минимум 3 буквы")
    ctx.db.set(key, ", ".join(words)[:300])
    r.args = []
    ui.view(r, "sr")
    return await breaks(ctx, r)


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
