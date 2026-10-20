"""Admin panel (shaxsiy chat): bosh menyu va tugma/matn yo'naltirish. Bo'limlar alohida modullarda."""
from __future__ import annotations

import contextvars
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from . import people as P
from . import ui
from .ui import Req, card, grid, h, kb, nav, onoff, screen, title

log = logging.getLogger("panel")
CUR_CHAT: contextvars.ContextVar = contextvars.ContextVar("panel_chat", default=None)


def _effect_watch():
    """Bot API so'rovlari: panel chatiga oddiy xabar (toast, panel) — ta'sir emas; boshqa chatga yoki fayl — ta'sir."""
    from aiogram.client.session.middlewares.base import BaseRequestMiddleware

    from .db import mark_effect

    class EffectWatch(BaseRequestMiddleware):
        async def __call__(self, make_request, bot, method):
            name = type(method).__name__
            if name.startswith(("Send", "Forward", "Copy")):
                cid = getattr(method, "chat_id", None)
                if not (name == "SendMessage" and cid is not None and str(cid) == str(CUR_CHAT.get())):
                    mark_effect()
            return await make_request(bot, method)
    return EffectWatch()

MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr",
             "dekabr"]
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
             "ноября", "декабря"]


def level_of(ctx, uid: int | None) -> str:
    return P.admin_level(ctx.db, ctx.cfg.owner_ids, uid)


def make_req(ctx, uid: int, chat_id: int, data: str = "", text: str = "", message=None) -> Req:
    return Req(uid=uid, chat_id=chat_id, level=level_of(ctx, uid), data=data, args=data.split(":")[1:] if data else [],
               text=text, message=message, lang=ctx.lang(uid))


# ───────────────────────── bosh menyu
@screen("m", "view")
async def main_menu(ctx, r: Req):
    db, now = ctx.db, int(ctx.clock())
    t = datetime.fromtimestamp(now, ctx.tz)
    months = MONTHS_RU if r.lang == "ru" else MONTHS_UZ
    when = f"{t.day} {months[t.month - 1]} · {t:%H:%M}"
    alive = db.flag("bot_enabled")
    from .timeutil import day_start
    d0 = day_start(now, ctx.tz)
    waiting = db.scalar("SELECT COUNT(*) FROM threads WHERE wait_since IS NOT NULL")
    delays = db.scalar("SELECT COUNT(*) FROM alerts WHERE created_ts>=? AND status<>'void'", (d0,))
    stavka = db.scalar("SELECT COUNT(*) FROM threads WHERE stavka='on'")
    staff = ctx.att.staff()
    day = t.date().isoformat()
    came = db.scalar("SELECT COUNT(*) FROM attendance WHERE day=? AND arrived_ts IS NOT NULL", (day,))
    lines = [f"<b>{r.L('Bugun', 'Сегодня')}</b>",
             f"⏱ {r.L('Javob kutyapti', 'Ждут ответа')} — <b>{waiting}</b>",
             f"🚨 {r.L('Zaderjka', 'Задержки')} — <b>{delays}</b>",
             f"🎬 {r.L('Stavkada', 'В ставке')} — <b>{stavka}</b>",
             f"🙋 {r.L('Ishda', 'На работе')} — <b>{came} / {len(staff)}</b>"]
    cash, ready = None, True
    if r.can("full"):
        from . import kassa as K
        from .kassa_view import money
        if K.zp_mode(db) != "off":                     # 💰 shu haftadagi jami oylik ($), dushanbadan beri
            ws = K.week_start(t.date())
            b = K.calc(db, ws, t.date())
            zp = sum(x["zp"] for x in b["rows"].values() if x["kind"] == "worker" and x["zp_on"])
            ready = K.zp_state(db, ws, t.date(), t.date())["ready"]
            cash = money(zp)
            lines.append(f"💰 Cash — <b>{'' if ready else '≈ '}{cash} $</b>")
    ub = ctx.userbot
    ub_ok = ub is not None and ub.state == "online"
    accs = db.all("SELECT id FROM accounts WHERE paused=0")
    online = sum(1 for a in accs if ctx.pool and ctx.pool.state_of(a["id"]) == "online")
    group_ok = bool(db.get("proyob_group_id"))
    sysline = (f"{'🟢' if ub_ok else '🔴'} {r.L('Akkaunt', 'Аккаунт')} · "
               f"{'🟢' if (not accs or online == len(accs)) else '🟡'} Push {online}/{len(accs)} · "
               f"{'🟢' if group_ok else '🔴'} «Проёб»")
    head = title("◆", "RD CONTROL", f"{when} · " + (r.L("🟢 ishlayapti", "🟢 работает") if alive else
                                                     r.L("⛔ to'xtatilgan", "⛔ остановлен")))
    from .kassa import pending_reports
    pend = len(pending_reports(db)) if r.can("full") else 0
    buttons = [(r.L("🚨 Nazorat", "🚨 Контроль"), "c"), (r.L("💵 Kassa", "💵 Касса") + (f" ❓{pend}" if pend else ""), "k"),
               (r.L("👥 Xodimlar", "👥 Сотрудники"), "p"), ("📣 Push", "u"),
               (r.L("📊 Hisobotlar", "📊 Отчёты"), "r"), (r.L("⚙️ Sozlamalar", "⚙️ Настройки"), "s")]
    if not r.can("full"):
        buttons = [b for b in buttons if b[1] in ("c", "p", "r")]
    rows = grid(buttons)
    rows.append([(r.L("🌐 Русский язык", "🌐 O'zbek tili"), r.L("lang:ru", "lang:uz")),
                 (r.L("🎨 Mavzu", "🎨 Тема"), "th")])
    from . import panel_cards as PC
    blocks = PC.main(r, t, alive, waiting, delays, stavka, came, len(staff), cash, ready, ub_ok, online, len(accs),
                     group_ok)
    return ui.rich(ui.join(head, "", card(lines), card([sysline])), blocks), kb(*rows)


@screen("lang", "view")
async def switch_lang(ctx, r: Req):
    """Til aniq tanlanadi (ikki marta bosilsa ham qaytib ketmaydi) va faqat shu adminga."""
    want = r.args[0] if r.args and r.args[0] in ("uz", "ru") else ("ru" if r.lang != "ru" else "uz")
    ctx.db.set(f"lang:{r.uid}", want)
    ctx.db.set("lang", want)                               # guruh/bildirishnomalar uchun — oxirgi tanlov
    r.lang = want
    ui.HIST.pop(r.uid, None)                               # eski tildagi ko'rinishlar «Orqaga»da chiqmasin
    await set_commands(ctx, r.uid)
    return await main_menu(ctx, r)


@screen("th", "view")
async def theme_menu(ctx, r: Req):
    """🎨 Mavzu: rasm-panel ranglari (10 xil), rasm/matn, tugma uslubi — har admin o'ziga."""
    from . import cards, look
    from . import panel_cards as PC
    db = ctx.db
    a = r.args[0] if r.args else ""
    if a in cards.THEMES:
        db.set(f"theme:{r.uid}", a)
    elif a == "img":
        db.set(f"cards:{r.uid}", "0" if look.cards_on(db, r.uid) else "1")
    elif a == "btn":
        db.set(f"btnstyle:{r.uid}", "0" if look.buttons_on(db, r.uid) else "1")
    if a:
        ui.view(r, "th")
    cur = look.theme_of(db, r.uid)
    img, btn = look.cards_on(db, r.uid), look.buttons_on(db, r.uid)
    names = list(cards.THEMES)
    items = [(f"{'● ' if k == cur else ''}{i + 1}. {cards.THEMES[k].name}", f"th:{k}") for i, k in enumerate(names)]
    rows = grid(items)
    rows.append([(r.L("🖼 Rasm-panel: ", "🖼 Картинки: ") + (r.L("yoq", "вкл") if img else r.L("o'chiq", "выкл")),
                  "th:img"),
                 (r.L("🔤 Tugmalar: ", "🔤 Кнопки: ") + (r.L("qalin", "жирные") if btn else r.L("oddiy", "обычные")),
                  "th:btn")])
    rows.append(nav(r))
    lines = [f"🎨 {r.L('Mavzu', 'Тема')} — <b>{h(cards.THEMES[cur].name)}</b>",
             f"🖼 {r.L('Rasm-panel', 'Картинки')} — {onoff(r, img)}",
             f"🔤 {r.L('Tugmalar', 'Кнопки')} — " + (r.L("qalin harflar, oq belgilar", "белые значки")
                                                    if btn else r.L("oddiy", "обычные"))]
    text = ui.join(title("🎨", r.L("MAVZU", "ТЕМА"), r.L("faqat siz uchun", "только для вас")), "", card(lines),
                   r.L("<i>Mavzuni bosing — darhol almashadi. Boshqa adminlarda o'zgarmaydi.</i>",
                       "<i>Нажмите тему — сразу сменится. У других админов не меняется.</i>"))
    return ui.rich(text, PC.theme_preview(r, cards.THEMES[cur].name)), kb(*rows)


async def refresh_panels(ctx, note: str = "") -> None:
    """Bot qayta ishga tushdi: yangi xabar yubormaymiz — mavjud panel joyida yangilanadi (chat toza).
    Panel hali yo'q egaga — bitta panel yuboriladi."""
    ui.STORE = ctx.db
    chats = set(ctx.notifier.owner_ids())
    for row in ctx.db.all("SELECT key FROM settings WHERE key LIKE 'panel:%' AND value<>''"):
        try:
            chats.add(int(row["key"].split(":", 1)[1]))
        except ValueError:
            pass
    for chat in chats:
        level = level_of(ctx, chat)
        if not level:
            continue
        req = Req(uid=chat, chat_id=chat, level=level, lang=ctx.lang(chat))
        try:
            text, markup = await main_menu(ctx, req)
            await ui.show(ctx.bot, chat, text, markup, styled=True)
            if note and level == "owner":
                await ui.toast(ctx.bot, chat, note, 30)
        except Exception as exc:
            log.info("Panel yangilanmadi %s: %s", chat, exc)


async def set_commands(ctx, uid: int | None = None) -> None:
    """«/» menyusi: shaxsiy chatda — panel buyruqlari, guruhda — faqat guruhda ishlaydiganlar (chalkashmasin).
    uid berilsa — faqat shu admin chatiga, uning tilida."""
    from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeChat
    ru = ctx.lang(uid) == "ru"
    private = [BotCommand(command="menu", description="◆ Меню" if ru else "◆ Menyu"),
               BotCommand(command="hisobot", description="📊 Отчёт за сегодня" if ru else "📊 Bugungi hisobot"),
               BotCommand(command="id", description="🆔 Мой ID" if ru else "🆔 Mening ID")]
    group = [BotCommand(command="statistika", description="📅 Итоги недели"),
             BotCommand(command="top", description="🏆 Касса за сегодня"),
             BotCommand(command="topyest", description="🏆 Касса за вчера"),
             BotCommand(command="topweek", description="🏆 Касса за неделю"),
             BotCommand(command="toplast", description="🏆 Касса за прошлую неделю"),
             BotCommand(command="topall", description="🏆 Касса — всего")]
    if uid:
        try:
            await ctx.bot.set_my_commands(private, scope=BotCommandScopeChat(chat_id=uid))
        except Exception:
            log.info("Buyruqlar (chat) o'rnatilmadi")
        return
    try:
        await ctx.bot.delete_my_commands()                 # umumiy (hamma chat) menyu — eski botdan qolmasin
        await ctx.bot.set_my_commands(private, scope=BotCommandScopeAllPrivateChats())
        await ctx.bot.set_my_commands(group, scope=BotCommandScopeAllGroupChats())
    except Exception:
        log.info("Buyruqlar o'rnatilmadi")


# ───────────────────────── yo'naltirish
def build_router(ctx) -> Router:
    from . import panel_control, panel_kassa, panel_people, panel_push, panel_reports, panel_settings, private  # noqa: F401
    from .db import EFFECTS
    r = Router(name="panel")
    ui.STORE = ctx.db
    try:
        ctx.bot.session.middleware(_effect_watch())
    except Exception:
        log.info("Effect middleware o'rnatilmadi")

    async def render(req: Req, res, edit_id=None, fresh=False, safe: bool = False):
        if res is None:
            return
        if isinstance(res, str):
            await ui.toast(ctx.bot, req.chat_id, res)
            return
        text, markup = res
        await ui.show(ctx.bot, req.chat_id, text, markup, edit_id=edit_id, fresh=fresh, styled=True)
        if edit_id:
            ctx.notifier.forget(req.chat_id, edit_id)       # savol xabari panelga aylandi
        ui.remember(req.uid, req.view or "?", text, markup, safe, ask=req.uid in ui.WAIT)

    async def run_screen(req: Req, data: str, edit_id: int) -> None:
        prefix = data.split(":")[0]
        entry = ui.SCREENS.get(prefix)
        if entry is None:
            return
        fn, need = entry
        if not req.can(need):
            await ui.toast(ctx.bot, req.chat_id, req.L("⛔ Bu amal uchun huquq yo'q", "⛔ Нет прав на это действие"))
            return
        ui.WAIT.pop(req.uid, None)
        eff = [0]
        EFFECTS.set(eff)
        CUR_CHAT.set(req.chat_id)
        try:
            res = await fn(ctx, req)
        except ui.Gone:
            await ui.toast(ctx.bot, req.chat_id, req.L("ℹ️ Bu yozuv o'chirilgan yoki birlashtirilgan",
                                                       "ℹ️ Эта запись удалена или объединена"))
            req.view, req.calls = None, 0
            res = await main_menu(ctx, req)
        except Exception:
            log.exception("Ekran xatosi: %s", data)
            res = req.L("⚠️ Xatolik, qayta urinib ko'ring", "⚠️ Ошибка, попробуйте ещё раз")
        finally:
            EFFECTS.set(None)
        safe = eff[0] == 0 or req.calls >= 2 or req.view_set
        await render(req, res, edit_id=edit_id, safe=safe)

    @r.callback_query(F.message.chat.type == "private")
    async def on_cb(cb: CallbackQuery) -> None:
        uid = cb.from_user.id
        data = cb.data or ""
        try:
            await cb.answer()                              # tugma darhol «javob beradi»
        except Exception:
            pass
        req = make_req(ctx, uid, cb.message.chat.id, data, message=cb.message)
        from .kassa import ACTOR
        ACTOR.set(uid)                                     # kassa tarixi: kim o'zgartirdi
        if not req.level:
            from . import private
            await private.on_worker_cb(ctx, cb, data)
            return
        if data == "bk" or data.startswith("bk:"):         # «‹ Orqaga» — oldingi ekran
            ui.WAIT.pop(uid, None)
            prev = ui.previous(uid)
            if prev is not None and not prev["safe"]:
                await ui.show(ctx.bot, req.chat_id, prev["text"], prev["markup"], edit_id=cb.message.message_id,
                              styled=True)
                return
            data = prev["data"] if prev is not None else (data[3:] or "m")
            req = make_req(ctx, uid, cb.message.chat.id, data, message=cb.message)
        await run_screen(req, data, cb.message.message_id)

    @r.message(F.chat.type == "private", Command("start", "menu"))
    async def on_menu(message: Message) -> None:
        req = make_req(ctx, message.from_user.id, message.chat.id)
        if not req.level:
            from . import private
            await private.on_start(ctx, message)
            return
        ui.WAIT.pop(req.uid, None)
        try:
            await message.delete()
        except Exception:
            pass
        await render(req, await main_menu(ctx, req), fresh=True, safe=True)

    @r.message(F.chat.type == "private", Command("hisobot", "otchet", "report"))
    async def on_report(message: Message) -> None:
        req = make_req(ctx, message.from_user.id, message.chat.id, data="r:td")
        if not req.level:
            return
        ui.WAIT.pop(req.uid, None)
        try:
            await message.delete()
        except Exception:
            pass
        from .panel_reports import reports_menu
        await render(req, await reports_menu(ctx, req), fresh=True, safe=True)

    @r.message(F.chat.type == "private", Command("ega", "owner"))
    async def on_recover(message: Message) -> None:
        """🔐 Ega akkaunti yo'qolsa: yangi akkauntdan «/ega KOD»."""
        from . import recovery
        u = message.from_user
        parts = (message.text or "").split(maxsplit=1)
        try:
            await message.delete()                          # kod chatda qolmasin
        except Exception:
            pass
        name = " ".join(x for x in (u.first_name, u.last_name) if x) or str(u.id)
        res, note = await recovery.try_code(ctx, u.id, name, parts[1] if len(parts) > 1 else "")
        replies = {"ok": "✅ Siz endi 👑 egasiz. /menu\n\nYangi tiklash kodi o'rnating: ⚙️ → 👮 Adminlar → 🔐",
                   "already": "👑 Siz allaqachon egasiz. /menu",
                   "none": "Tiklash kodi o'rnatilmagan.",
                   "limit": "⛔ Bugun urinishlar tugadi. Ertaga qayta urinib ko'ring.",
                   "bad": "⚠️ Kod noto'g'ri."}
        try:
            await message.answer(replies.get(res, "⚠️"))
        except Exception:
            pass
        for oid in (ctx.notifier.owner_ids() if note else []):
            if oid != u.id:                                 # boshqa egalarga xabar
                try:
                    await ctx.bot.send_message(oid, note, parse_mode="HTML")
                except Exception:
                    pass

    @r.message(F.chat.type == "private", Command("id"))
    async def on_id(message: Message) -> None:
        await message.answer(f"🆔 <code>{message.from_user.id}</code>", parse_mode="HTML")

    @r.message(F.chat.type == "private")
    async def on_message(message: Message) -> None:
        uid = message.from_user.id if message.from_user else None
        req = make_req(ctx, uid, message.chat.id, text=(message.text or message.caption or "").strip(), message=message)
        if not req.level:
            from . import private
            await private.on_text(ctx, message)
            return
        state = ui.WAIT.get(uid)
        from .kassa import ACTOR
        ACTOR.set(uid)
        if state is None and req.text and req.can("full"):  # hisobot / jarima shu yerga yozilsa — qabul qilinadi
            from . import kassa_flow
            try:
                res = await kassa_flow.private_entry(ctx, req, message)
            except Exception:
                log.exception("Shaxsiy chatdagi hisobot")
                res = None
            if res is not None:
                try:
                    await message.delete()
                except Exception:
                    pass
                await render(req, res)
                return
        if message.forward_origin is not None and state is None:
            await render(req, forward_info(req, message))
            return
        if state is None:
            try:
                await message.delete()
            except Exception:
                pass
            await render(req, await main_menu(ctx, req), fresh=True, safe=True)
            return
        entry = ui.INPUTS.get(state["act"])
        if entry is None:
            ui.WAIT.pop(uid, None)
            return
        fn, need = entry
        if not req.can(need):
            ui.WAIT.pop(uid, None)
            return
        try:
            res = await fn(ctx, req, **state["data"])
        except ui.Gone:
            ui.WAIT.pop(uid, None)
            res = await main_menu(ctx, req)
        except Exception:
            log.exception("Kiritish xatosi: %s", state["act"])
            res = req.L("⚠️ Xatolik, qayta urinib ko'ring", "⚠️ Ошибка, попробуйте ещё раз")
        try:
            await message.delete()                          # chat toza: kiritilgan xabar (kod, parol ham) o'chadi
        except Exception:
            pass
        if isinstance(res, str):                           # xato — yana kutamiz
            await ui.toast(ctx.bot, req.chat_id, res, 6)
            return
        if ui.WAIT.get(uid) is state:
            ui.WAIT.pop(uid, None)
        await render(req, res, safe=req.calls >= 1 or req.view_set)

    return r


def forward_info(r: Req, message: Message):
    """Boshqa chatdan yuborilgan xabar — ID ni ko'rsatish (sozlash uchun)."""
    o = message.forward_origin
    kind = getattr(o, "type", "")
    if kind == "user":
        u = o.sender_user
        name = " ".join(x for x in (u.first_name, u.last_name) if x)
        text = f"👤 <b>{h(name)}</b>{' @' + h(u.username) if u.username else ''}\nID: <code>{u.id}</code>"
    elif kind in ("chat", "channel"):
        c = getattr(o, "sender_chat", None) or getattr(o, "chat", None)
        text = f"👥 <b>{h(c.title or '')}</b>\nID: <code>{c.id}</code>"
    else:
        text = r.L("🙈 Yuboruvchi o'z akkauntini yashirgan.", "🙈 Отправитель скрыл аккаунт.")
    return text, kb([(r.L("⌂ Menyu", "⌂ Меню"), "m")])
