"""Admin panel (shaxsiy chat): bosh menyu va tugma/matn yo'naltirish. Bo'limlar alohida modullarda."""
from __future__ import annotations

import contextvars
import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from . import people as P
from . import ui
from .ui import Req, card, grid, h, kb, screen, title

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
    from .context import LANG
    lang = ctx.lang(uid)
    LANG.set(lang)                  # shu so'rov davomida chiqadigan hamma matn (savollar ham) — shu admin tilida
    return Req(uid=uid, chat_id=chat_id, level=level_of(ctx, uid), data=data, args=data.split(":")[1:] if data else [],
               text=text, message=message, lang=lang)


# ───────────────────────── bosh menyu
@screen("m", "view")
async def main_menu(ctx, r: Req):
    ui.view(r, "m")                     # qayerdan ochilsa ham (til almashtirish, /start …) — jonli yangilanadi
    db, now = ctx.db, int(ctx.clock())
    t = datetime.fromtimestamp(now, ctx.tz)
    months = MONTHS_RU if r.lang == "ru" else MONTHS_UZ
    when = f"{t.day} {months[t.month - 1]} · {t:%H:%M}"
    alive = db.flag("bot_enabled")
    from .timeutil import day_start
    d0 = day_start(now, ctx.tz)
    lc = ctx.tracker.live_counts(now) if ctx.tracker else {"waiting": 0, "stavka": 0, "overdue": {}}
    waiting, stavka = lc["waiting"], lc["stavka"]
    delays = db.scalar("SELECT COUNT(*) FROM alerts WHERE created_ts>=? AND status<>'void'", (d0,))
    staff = ctx.att.staff()
    day = t.date().isoformat()
    came = db.scalar("SELECT COUNT(*) FROM attendance WHERE day=? AND arrived_ts IS NOT NULL", (day,))
    lines = [f"<b>{r.L('Bugun', 'Сегодня')}</b>",
             f"⏱ {r.L('Javob kutyapti', 'Ждут ответа')} — <b>{waiting}</b>",
             f"🚨 {r.L('Zaderjkalar', 'Задержки')} — <b>{delays}</b>",
             f"🎬 {r.L('Stavkada', 'В ставке')} — <b>{stavka}</b>",
             f"🙋 {r.L('Ishda', 'На работе')} — <b>{came} / {len(staff)}</b>"]
    if r.owner:                                        # 💰 shu hafta (dushanbadan) ishlangan jami kassa, $
        from . import kassa as K
        from .kassa_view import money
        b = K.calc(db, K.week_start(t.date()), t.date())
        cash = sum(x["usd"] for x in b["rows"].values() if x["kind"] != "partner")
        lines.append(f"💰 Cash — <b>{money(cash)} $</b> <i>({r.L('dushanbadan', 'с понедельника')})</i>")
    # papkalar bo'yicha hozirgi zaderjkalar: 🟢 yo'q · 🟡 bor · 🔴 ko'p (jarima chegarasi)
    over = lc["overdue"]
    red = max(1, ctx.tracker.fine_rules()[0]) if ctx.tracker else 3
    live = [f"<b>{r.L('Hozir zaderjka', 'Задержки сейчас')}</b>"]
    if not db.flag("delay_enabled"):
        live.append(r.L("⚪ nazorat o'chiq", "⚪ контроль выключен"))
    for f in P.folders(db):
        if not f["delay_on"] or not db.flag("delay_enabled"):
            continue
        n = over.get(f["id"], 0)
        live.append(f"{'🟢' if n == 0 else ('🔴' if n >= red else '🟡')} {h(f['name'])} — <b>{n}</b>")
    ub = ctx.userbot
    ub_ok = ub is not None and ub.state == "online"
    accs = db.all("SELECT id FROM accounts WHERE paused=0")
    online = sum(1 for a in accs if ctx.pool and ctx.pool.state_of(a["id"]) == "online")
    group_ok = bool(db.get("proyob_group_id"))
    sysline = (f"{'🟢' if ub_ok else '🔴'} {r.L('Akkaunt', 'Аккаунт')} · "
               f"{'🟢' if (not accs or online == len(accs)) else '🟡'} {r.L('Push', 'Пуш')} {online}/{len(accs)} · "
               f"{'🟢' if group_ok else '🔴'} «Проёб»")
    pu = ctx.pusher
    pushline = (f"📣 {r.L('Push ketyapti', 'Идёт Пуш')} — <b>{h(pu.progress_text or '…')}</b>"
                if pu is not None and pu.running else None)
    head = title("◆", "RD CONTROL", f"{when} · " + (r.L("🟢 ishlayapti", "🟢 работает") if alive else
                                                     r.L("⛔ to'xtatilgan", "⛔ остановлен")))
    from .kassa import pending_reports
    pend = len(pending_reports(db)) if r.can("full") else 0
    buttons = [(r.L("🚨 Nazorat", "🚨 Контроль"), "c"), (r.L("💵 Kassa", "💵 Касса") + (f" ❓{pend}" if pend else ""), "k"),
               (r.L("👥 Xodimlar", "👥 Сотрудники"), "p"), (r.L("📣 Push", "📣 Пуш"), "u"),
               (r.L("📊 Hisobotlar", "📊 Отчёты"), "r"), (r.L("⚙️ Sozlamalar", "⚙️ Настройки"), "s")]
    if not r.can("full"):
        buttons = [b for b in buttons if b[1] in ("c", "p", "r")]
    rows = grid(buttons)
    rows.append([(r.L("🌐 Русский язык", "🌐 O'zbek tili"), r.L("lang:ru", "lang:uz"))])
    return ui.join(head, "", card(lines), card(live) if len(live) > 1 else "", card([sysline, pushline])), kb(*rows)


# ───────────────────────── jonli panel: bosh menyu va Push o'z joyida yangilanib turadi
LIVE_VIEWS = ("m", "u")
_LIVE_PAUSE: dict[int, float] = {}
LIVE_EVERY = 1                          # soniya: har soniyada tekshiriladi, son o'zgarsa — o'sha xabar tahrirlanadi


async def live_refresh(ctx) -> int:
    """Panelda bosh menyu (yoki Push) ochiq turgan chatlar: raqamlar o'zgargan bo'lsa — xabar JOYIDA tahrirlanadi
    (yangi xabar yo'q, bildirishnoma yo'q, panel o'chib-yonmaydi). -> nechta tahrirlandi."""
    import time as _t

    from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
    from aiogram.types import LinkPreviewOptions
    n = 0
    for chat, view in list(ui.VIEW.items()):
        base = (view or "").split(":")[0]                  # «m:ru» (til almashtirilgandan keyin) ham — bosh menyu
        if base not in LIVE_VIEWS or _t.monotonic() < _LIVE_PAUSE.get(chat, 0) or chat in ui.WAIT:
            continue
        async with ui.lock(chat):
            mid = ui.panel_id(chat)
            if ui.VIEW.get(chat) != view or not mid:
                continue                                   # foydalanuvchi boshqa ekranga o'tdi
            req = make_req(ctx, chat, chat, base)
            fn, need = ui.SCREENS[base]
            if not req.can(need):
                ui.VIEW.pop(chat, None)
                continue
            res = await fn(ctx, req)
            if not isinstance(res, tuple) or res[0] == ui.SHOWN.get(chat):
                continue
            text, markup = res
            try:
                await ctx.bot.edit_message_text(text, chat_id=chat, message_id=mid, reply_markup=markup,
                                                parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
                ui.SHOWN[chat] = text
                n += 1
            except TelegramRetryAfter as exc:              # Telegram «sekinroq» dedi — shu chatda biroz kutamiz
                _LIVE_PAUSE[chat] = _t.monotonic() + exc.retry_after
            except TelegramBadRequest as exc:
                if "not modified" in str(exc).lower():
                    ui.SHOWN[chat] = text
                else:
                    ui.VIEW.pop(chat, None)                # panel o'chirilgan — kuzatmaymiz
            except Exception as exc:
                log.info("Jonli panel %s: %s", chat, type(exc).__name__)
    return n


async def live_loop(ctx) -> None:
    import asyncio
    while True:
        await asyncio.sleep(LIVE_EVERY)
        try:
            await live_refresh(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Jonli panel")


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
            await ui.show(ctx.bot, chat, text, markup, view="m")
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
             BotCommand(command="topweek", description="🏆 Касса — эта неделя"),
             BotCommand(command="toplast", description="🏆 Касса — прошлая неделя"),
             BotCommand(command="topall", description="🏆 Касса — всего (по сегодня)"),
             BotCommand(command="frozen", description="💤 Застывшие лиды (каждая RD отдельно)"),
             BotCommand(command="cooling", description="📉 Остывающие лиды (каждая RD отдельно)"),
             BotCommand(command="clean", description="🧹 Удалить задержки, на которые уже ответили")]
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
    from . import (panel_control, panel_insights, panel_kassa, panel_people, panel_push, panel_reports,  # noqa: F401
                   panel_settings, private)
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
        async with ui.lock(req.chat_id):
            await ui.show(ctx.bot, req.chat_id, text, markup, edit_id=edit_id, fresh=fresh,
                          view=None if req.uid in ui.WAIT else req.view)
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
        chat = cb.message.chat.id
        before, shown = ui.VIEW.get(chat), ui.SHOW_N.get(chat, 0)
        ui.VIEW[chat] = None                               # tugma bosildi — jonli yangilanish bu panelga tegmaydi
        try:
            await _on_cb(req, uid, data, cb)
        finally:
            if ui.SHOW_N.get(chat, 0) == shown and ui.VIEW.get(chat) is None:
                ui.VIEW[chat] = before                     # ekran o'zgarmadi (faqat bildirishnoma) — qaytadi

    async def _on_cb(req: Req, uid: int, data: str, cb: CallbackQuery) -> None:
        if data == "bk" or data.startswith("bk:"):         # «‹ Orqaga» — oldingi ekran
            ui.WAIT.pop(uid, None)
            prev = ui.previous(uid)
            if prev is not None and not prev["safe"]:
                await ui.show(ctx.bot, req.chat_id, prev["text"], prev["markup"], edit_id=cb.message.message_id)
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
            if re.fullmatch(r"[\d\s\-]{5,15}", req.text or "") and 5 <= len(re.sub(r"\D", "", req.text)) <= 6:
                await ui.toast(ctx.bot, req.chat_id, req.L(          # kirish kodi — lekin kirish boshlanmagan
                    "⚠️ Kod kutilmayotgan edi. Akkaunt ulash: ⚙️ Sozlamalar → 🔑 Asosiy akkaunt → 📲 Ulash",
                    "⚠️ Код не ожидался. Подключение: ⚙️ Настройки → 🔑 Основной аккаунт → 📲 Подключить"), 8)
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
