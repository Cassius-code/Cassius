"""Admin panel (shaxsiy chat): bosh menyu va tugma/matn yo'naltirish. Bo'limlar alohida modullarda."""
from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from . import people as P
from . import ui
from .ui import Req, card, grid, h, kb, screen, title

log = logging.getLogger("panel")

MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr",
             "dekabr"]
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
             "ноября", "декабря"]


def level_of(ctx, uid: int | None) -> str:
    return P.admin_level(ctx.db, ctx.cfg.owner_ids, uid)


def make_req(ctx, uid: int, chat_id: int, data: str = "", text: str = "", message=None) -> Req:
    return Req(uid=uid, chat_id=chat_id, level=level_of(ctx, uid), data=data, args=data.split(":")[1:] if data else [],
               text=text, message=message, lang=ctx.lang())


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
    if r.can("full"):
        from . import kassa as K
        from .kassa_view import money
        b = K.calc(db, t.date(), t.date())
        lines.append(f"💵 {r.L('Kassa', 'Касса')} — <b>{money(b['K'])} $</b>")
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
    rows.append([(r.L("🌐 Til: O'zbekcha", "🌐 Язык: Русский"), "lang")])
    return ui.join(head, "", card(lines), card([sysline])), kb(*rows)


@screen("lang", "view")
async def switch_lang(ctx, r: Req):
    ctx.db.set("lang", "ru" if ctx.lang() != "ru" else "uz")
    r.lang = ctx.lang()
    await set_commands(ctx)
    return await main_menu(ctx, r)


async def set_commands(ctx) -> None:
    """«/» menyusi: shaxsiy chatda — panel buyruqlari, guruhda — faqat guruhda ishlaydiganlar (chalkashmasin)."""
    from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
    ru = ctx.lang() == "ru"
    private = [BotCommand(command="menu", description="◆ Меню" if ru else "◆ Menyu"),
               BotCommand(command="hisobot", description="📊 Отчёт за сегодня" if ru else "📊 Bugungi hisobot"),
               BotCommand(command="id", description="🆔 Мой ID" if ru else "🆔 Mening ID")]
    group = [BotCommand(command="statistika", description="📅 Итоги недели"),
             BotCommand(command="top", description="🏆 Касса за сегодня"),
             BotCommand(command="topyest", description="🏆 Касса за вчера"),
             BotCommand(command="topweek", description="🏆 Касса за неделю"),
             BotCommand(command="toplast", description="🏆 Касса за прошлую неделю")]
    try:
        await ctx.bot.delete_my_commands()                 # umumiy (hamma chat) menyu — eski botdan qolmasin
        await ctx.bot.set_my_commands(private, scope=BotCommandScopeAllPrivateChats())
        await ctx.bot.set_my_commands(group, scope=BotCommandScopeAllGroupChats())
    except Exception:
        log.info("Buyruqlar o'rnatilmadi")


# ───────────────────────── yo'naltirish
def build_router(ctx) -> Router:
    from . import panel_control, panel_kassa, panel_people, panel_push, panel_reports, panel_settings, private  # noqa: F401
    r = Router(name="panel")

    async def render(req: Req, res, edit_id=None, fresh=False):
        if res is None:
            return
        if isinstance(res, str):
            await ui.toast(ctx.bot, req.chat_id, res)
            return
        text, markup = res
        await ui.show(ctx.bot, req.chat_id, text, markup, edit_id=edit_id, fresh=fresh)

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
        prefix = data.split(":")[0]
        entry = ui.SCREENS.get(prefix)
        if entry is None:
            return
        fn, need = entry
        if not req.can(need):
            await ui.toast(ctx.bot, req.chat_id, req.L("⛔ Bu amal uchun huquq yo'q", "⛔ Нет прав на это действие"))
            return
        ui.WAIT.pop(uid, None)
        try:
            res = await fn(ctx, req)
        except ui.Gone:
            await ui.toast(ctx.bot, req.chat_id, req.L("ℹ️ Bu yozuv o'chirilgan yoki birlashtirilgan",
                                                       "ℹ️ Эта запись удалена или объединена"))
            res = await main_menu(ctx, req)
        except Exception:
            log.exception("Ekran xatosi: %s", data)
            res = req.L("⚠️ Xatolik, qayta urinib ko'ring", "⚠️ Ошибка, попробуйте ещё раз")
        await render(req, res, edit_id=cb.message.message_id)

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
        await render(req, await main_menu(ctx, req), fresh=True)

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
        await render(req, await reports_menu(ctx, req), fresh=True)

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
        if message.forward_origin is not None and state is None:
            await render(req, forward_info(req, message))
            return
        if state is None:
            try:
                await message.delete()
            except Exception:
                pass
            await render(req, await main_menu(ctx, req), fresh=True)
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
        await render(req, res)

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
