"""«Проёб» guruhi: «доброе утро» va tanaffuslar, kassa cheklari va jarima/bonuslar, «✅ Выполнено» tugmasi,
/proyob /statistika /top /id buyruqlari. Bot boshqa guruhlarda hech narsa o'qimaydi va yozmaydi."""
from __future__ import annotations

import logging
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from . import kassa as K
from . import kassa_flow
from . import people as P
from . import ui
from .attendance import norm
from .kassa_view import num, rating_plain
from .reports import weekly_group
from .timeutil import local_date
from .ui import Req, card, h, kb, screen

log = logging.getLogger("group")

GROUPS = {"group", "supergroup"}
TOP_CMDS = {"topweek": "tw", "toplast": "lw", "topall": "all"}   # shu hafta · o'tgan hafta · shu kungacha
REACT = {"arrived": "👍", "greeted": "👍", "break_start": "👌", "break_end": "👍", "break_end_late": "👍"}


def is_proyob(ctx, chat_id: int) -> bool:
    return str(chat_id) == (ctx.db.get("proyob_group_id") or "").strip()


def sender_info(ctx, message: Message) -> tuple[int | None, bool, str]:
    """-> (user_id, staff (ega/to'liq admin yoki anonim admin), ism)."""
    anon = message.sender_chat is not None and message.sender_chat.id == message.chat.id
    if anon:
        return None, True, message.author_signature or "admin"
    u = message.from_user
    if u is None or u.is_bot:
        return None, False, ""
    level = P.admin_level(ctx.db, ctx.cfg.owner_ids, u.id)
    name = " ".join(x for x in (u.first_name, u.last_name) if x) or str(u.id)
    return u.id, level in ("owner", "full"), name


async def react(ctx, message: Message, emoji: str) -> None:
    try:
        from aiogram.types import ReactionTypeEmoji
        await ctx.bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id,
                                           reaction=[ReactionTypeEmoji(emoji=emoji)])
    except Exception:
        pass


NOTIFIER = None                 # «Проёб»ga asosiy akkaunt nomidan yozish tanlansa — javoblar ham o'sha nomdan


async def reply(message: Message, text: str, trash: str | None = None) -> None:
    """Faqat «Проёб» da (qulf boshqasini o'tkazmaydi). Matn — HTML (gtext.esc bilan).
    trash="info" — avtomat xabar, vaqti kelganda o'chadi (buyruqqa javoblar — o'chmaydi)."""
    if NOTIFIER is not None and NOTIFIER._main() is not None and is_proyob(SimpleNamespace(db=NOTIFIER.db),
                                                                            message.chat.id):
        try:
            await NOTIFIER.send_group(text, reply_to=message.message_id, trash=trash)
            return
        except Exception as exc:
            log.info("Guruhga javob (asosiy akkaunt) yozilmadi: %s", exc)
    try:
        sent = await message.reply(text, disable_web_page_preview=True, parse_mode="HTML")
        if trash and NOTIFIER is not None:
            NOTIFIER.trash(sent.chat.id, sent.message_id, trash)
    except Exception as exc:
        log.info("Guruhga javob yozilmadi: %s", exc)


async def attendance_reply(ctx, message: Message, person, ev: dict, ts: int) -> None:
    """Ishga kelish / tanaffus natijasi «Проёб»da: kech qolsa — xabar; tanaffus — «☕ @baxa — перерыв до 14:30»;
    «тут» — 👍; «доброе утро» — 👍. Oddiy xabar bilan kelgan bo'lsa (kech emas) — jim."""
    arrive, br = ev.get("arrive"), ev.get("break")
    if arrive == "late":
        day = local_date(ts, ctx.tz)
        row = ctx.db.one("SELECT late_min FROM attendance WHERE day=? AND person_id=?", (day.isoformat(), person["id"]))
        await reply(message, ctx.att.late_text(person, row["late_min"] if row else 0, ts),
                    trash=None if ctx.att.late_fined(person["id"], day) else "info")
    elif arrive in ("arrived", "greeted") and ev.get("cmd") and not br:
        await react(ctx, message, "👍")
    if br == "break_start":
        await reply(message, ctx.att.break_text(person, ts), trash="info")
    elif br in ("break_end", "break_end_late"):
        await react(ctx, message, REACT[br])
    elif br == "break_limit":
        await reply(message, f"⛔ перерыв · {h(P.mention(person))} — перерывы на сегодня "
                             f"закончились ({ctx.db.get_int('breaks_per_day', 3)})", trash="info")


def group_lock(ctx):
    """🔒 Bot guruhlardan FAQAT «Проёб» ga yozadi. Boshqa guruh/chatga (lidlarga) xabar, reaksiya, tahrir — texnik
    jihatdan to'xtatiladi (Bot API so'rovi umuman ketmaydi). Shaxsiy chatlar (siz, adminlar) — mumkin."""
    from aiogram.client.session.middlewares.base import BaseRequestMiddleware
    from aiogram.exceptions import TelegramForbiddenError

    names = {"SetMessageReaction", "PinChatMessage", "UnpinChatMessage", "UnpinAllChatMessages", "SendChatAction",
             "EditMessageText", "EditMessageCaption", "EditMessageMedia", "EditMessageReplyMarkup"}

    class GroupLock(BaseRequestMiddleware):
        async def __call__(self, make_request, bot, method):
            name = type(method).__name__
            if name.startswith(("Send", "Forward", "Copy")) or name in names:
                cid = getattr(method, "chat_id", None)
                private = isinstance(cid, int) and cid > 0
                if cid is not None and not private and str(cid) != (ctx.db.get("proyob_group_id") or "").strip():
                    log.warning("🔒 %s → %s to'xtatildi: bot faqat «Проёб» ga yozadi", name, cid)
                    raise TelegramForbiddenError(method=method, message="locked: bot writes only to «Проёб»")
            return await make_request(bot, method)
    return GroupLock()


async def clean_delays(ctx) -> tuple[int, int]:
    """Hamma havolasi yopilgan «задержка» xabarlarini «Проёб»dan o'chirish. -> (o'chirildi, 48 soatdan eski)."""
    import time as _t
    db, now = ctx.db, int(_t.time())
    n = old = 0
    # «ochiq» — lid hali shu havola bo'yicha javob kutyapti (kun oxirida kutish yopilganlari ochiq hisoblanmaydi)
    for row in db.all("SELECT a.group_chat_id gid, a.group_msg_id mid, MIN(a.created_ts) sent, "
                      "SUM(CASE WHEN a.status='open' AND EXISTS (SELECT 1 FROM threads t WHERE t.alert_id=a.id) "
                      "THEN 1 ELSE 0 END) open FROM alerts a WHERE a.group_msg_id IS NOT NULL "
                      "GROUP BY a.group_chat_id, a.group_msg_id"):
        if row["open"]:
            continue                                      # hali javob kutayotgan havola bor — qoladi
        if now - row["sent"] > 47 * 3600:
            old += 1
            continue
        if await ctx.notifier.delete_group(row["gid"], row["mid"]):
            db.run("UPDATE alerts SET group_msg_id=NULL WHERE group_chat_id=? AND group_msg_id=?", (row["gid"], row["mid"]))
            n += 1
    return n, old


def build_router(ctx) -> Router:
    global NOTIFIER
    NOTIFIER = ctx.notifier
    r = Router(name="group")
    try:
        ctx.bot.session.middleware(group_lock(ctx))
    except Exception:
        log.warning("🔒 Guruh qulfi o'rnatilmadi")
    in_group = F.chat.type.in_(GROUPS)

    # ───────────── buyruqlar
    @r.message(in_group, Command("proyob"))
    async def cmd_proyob(message: Message) -> None:
        uid, _staff, _n = sender_info(ctx, message)
        if uid is None or P.admin_level(ctx.db, ctx.cfg.owner_ids, uid) not in ("owner", "full"):
            return                                       # begona guruhda jim
        ctx.db.set("proyob_group_id", str(message.chat.id))
        await reply(message, "✅ Эта группа подключена как «Проёб».")

    @r.message(in_group, Command("id"))
    async def cmd_id(message: Message) -> None:
        if is_proyob(ctx, message.chat.id):
            await reply(message, f"🆔 Группа: {message.chat.id}")
            return
        uid, _staff, _n = sender_info(ctx, message)       # boshqa guruh: ID — so'raganga shaxsan (admin bo'lsa)
        if uid is not None and P.admin_level(ctx.db, ctx.cfg.owner_ids, uid):
            try:
                await ctx.bot.send_message(uid, f"🆔 {h(message.chat.title or '')}: <code>{message.chat.id}</code>",
                                           parse_mode="HTML")
            except Exception:
                pass

    @r.message(in_group, Command("statistika", "stat"))
    async def cmd_stat(message: Message) -> None:
        if not is_proyob(ctx, message.chat.id):
            return
        t = local_date(ctx.clock(), ctx.tz)
        s = K.week_start(t)
        await reply(message, weekly_group(ctx, s, t))

    # 💤 /frozen (qotib qolgan) va 📉 /cooling (soviyotgan) — «Проёб»ga, HAR RD alohida xabar (ega va to'liq adminlar)
    @r.message(in_group, Command("frozen", "cooling"))
    async def cmd_lists(message: Message) -> None:
        if not is_proyob(ctx, message.chat.id):
            return
        _uid, staff, _n = sender_info(ctx, message)
        if not staff:
            return
        cmd = (message.text or "").split()[0].split("@")[0].lstrip("/").lower()
        kind, key = ("stale", "an_stale") if cmd == "frozen" else ("cool", "an_cooling")
        if not ctx.db.flag(key):
            await reply(message, "<i>функция выключена (панель → 🧩 Доп. функции)</i>")
            return
        from .panel_insights import post_lists
        if await post_lists(ctx, kind) == 0:
            await reply(message, "<i>" + ("застывших лидов нет" if kind == "stale" else "остывающих лидов нет") + "</i>")

    # 🧹 /clean — shu paytgacha javob berilgan «задержка» xabarlarini o'chirish (javob kutayotganlari qoladi)
    @r.message(in_group, Command("clean"))
    async def cmd_clean(message: Message) -> None:
        if not is_proyob(ctx, message.chat.id):
            return
        _uid, staff, _n = sender_info(ctx, message)
        if not staff:
            return
        n, old = await clean_delays(ctx)
        try:
            await message.delete()
        except Exception:
            pass
        text = f"🧹 удалено задержек: {n}" + (f" · старше 48 ч (Telegram не даёт удалить): {old}" if old else "")
        try:
            sent = await ctx.notifier.send_group(f"<i>{text}</i>")
        except Exception:
            return

        async def later():
            import asyncio
            await asyncio.sleep(8)
            await ctx.notifier.delete_group(*sent)
        ui.bg(later())

    # 🏆 reyting: /topweek — shu hafta, /toplast — o'tgan hafta, /topall — shu kungacha (boshlang'ich kassa bilan)
    @r.message(in_group, Command(*TOP_CMDS))
    async def cmd_top(message: Message) -> None:
        if not is_proyob(ctx, message.chat.id):
            return
        _uid, staff, _n = sender_info(ctx, message)
        if not staff:
            return
        cmd = (message.text or "").split()[0].split("@")[0].lstrip("/").lower()
        t = local_date(ctx.clock(), ctx.tz)
        if TOP_CMDS.get(cmd) == "all":
            items = K.cumulative_rating(ctx.db, t)
            from .gtext import card_lines, esc
            medal = ["🥇", "🥈", "🥉"]
            lines = [f"{medal[i] if i < 3 else f'{i + 1}.'} {esc(n)} — <b>{num(v)}</b>" for i, (n, v, _p) in
                     enumerate(items)]
            await reply(message, "\n".join(["🏆 <b>Рейтинг кассы</b> · всего", card_lines(lines or ["данных нет"])]))
            return
        s, e = K.period_range(TOP_CMDS.get(cmd, "td"), t)
        await reply(message, rating_plain(K.calc(ctx.db, s, e), s, e))

    # ───────────── «✅ Выполнено»
    @r.callback_query(F.data.startswith("al:"), F.message.chat.type.in_(GROUPS))
    async def on_done(cb: CallbackQuery) -> None:
        try:
            aid = int(cb.data.split(":")[1])
        except (ValueError, IndexError):
            await cb.answer()
            return
        u = cb.from_user
        who = f"@{u.username}" if u.username else (u.first_name or str(u.id))
        try:
            n = await ctx.tracker.press_done(aid, who)
        except Exception:
            log.exception("Выполнено")
            n = 0
        try:
            await cb.answer("✅ Отмечено" if n else "Уже закрыто")
        except Exception:
            pass

    @r.callback_query(F.message.chat.type.in_(GROUPS))
    async def on_other_cb(cb: CallbackQuery) -> None:
        try:
            await cb.answer()
        except Exception:
            pass

    # ───────────── matnlar
    async def handle(message: Message, edited: bool) -> None:
        if message.migrate_to_chat_id and is_proyob(ctx, message.chat.id):
            ctx.db.set("proyob_group_id", str(message.migrate_to_chat_id))
            return
        pm = message.pinned_message                       # «bot qadadi …» xizmat xabari — doska uchun keraksiz
        if pm is not None and str(pm.message_id) == ctx.db.get("board_msg_id"):
            try:
                await message.delete()
            except Exception:
                pass
            return
        if not is_proyob(ctx, message.chat.id) or not ctx.db.flag("bot_enabled"):
            return
        text = (message.text or message.caption or "").strip()
        if ctx.notifier.is_own(text):
            return                                         # bot o'zi asosiy akkaunt orqali yozgan xabar
        if not text or text.startswith("/"):
            return
        if not edited and len(text) <= 20 and norm(text) in ("statistika", "statistik"):   # eski botdagidek
            t = local_date(ctx.clock(), ctx.tz)
            await reply(message, weekly_group(ctx, K.week_start(t), t))
            return
        uid, staff, name = sender_info(ctx, message)
        if uid is None and not staff:
            return
        K.ACTOR.set(uid)
        if not edited and uid is not None:
            person = P.identify(ctx.db, uid, message.from_user.username)
            if person is not None:
                ts = int(message.date.timestamp())
                ev = await ctx.att.on_text(person, text, ts, report=K.looks_like_report(ctx.db, text))
                await attendance_reply(ctx, message, person, ev, ts)
                if ev.get("cmd"):
                    return                                  # tanaffus / qaytish / «доброе утро» — hisobot emas
        try:
            await kassa_flow.on_group_text(ctx, message, text, staff, uid, name)
        except Exception:
            log.exception("Kassa: guruh xabari")

    @r.message(in_group)
    async def on_message(message: Message) -> None:
        await handle(message, edited=False)

    @r.edited_message(in_group)
    async def on_edited(message: Message) -> None:
        await handle(message, edited=True)

    # ───────────── bot guruhga qo'shildi
    @r.my_chat_member(F.chat.type.in_(GROUPS))
    async def on_added(ev: ChatMemberUpdated) -> None:
        new = ev.new_chat_member.status
        if new not in ("member", "administrator") or ev.old_chat_member.status in ("member", "administrator"):
            return
        if is_proyob(ctx, ev.chat.id):
            return
        def build():                                       # har egaga o'z tilida
            lang = ctx.lang()
            L = (lambda uz, ru: ru if lang == "ru" else uz)
            text = ui.join(f"<b>➕ {L('BOT GURUHGA QO‘SHILDI', 'БОТА ДОБАВИЛИ В ГРУППУ')}</b>", "", card(
                [f"👥 {h(ev.chat.title or '')} · <code>{ev.chat.id}</code>",
                 L("Shu guruh «Проёб» bo'lsinmi? (xodimlar, kassa cheklari, zaderjkalar shu yerda)",
                   "Сделать эту группу «Проёб»? (сотрудники, чеки кассы, задержки — здесь)")]))
            return text, kb([(L("✅ Ha, «Проёб»", "✅ Да, «Проёб»"), f"sgset:{ev.chat.id}")],
                            [(L("✖️ Yo'q", "✖️ Нет"), f"sgno:{ev.chat.id}")])
        await ctx.notifier.send_keyed(ctx.notifier.owner_ids(), build, key=f"grp:{ev.chat.id}")

    return r


@screen("sgset", "owner")
async def set_group(ctx, r: Req):
    """Bitta ega «Ha» desa — boshqa egalardagi savol ham o'chadi."""
    gid = r.args[0]
    if not ctx.notifier.has_key(f"grp:{gid}") and ctx.db.get("proyob_group_id") == gid:
        return r.L("✅ Allaqachon belgilangan", "✅ Уже задана")
    ctx.db.set("proyob_group_id", gid)
    await ctx.notifier.resolve(f"grp:{gid}")
    await ui.toast(ctx.bot, r.chat_id, r.L("✅ «Проёб» belgilandi. Botni guruhda admin qiling.",
                                           "✅ «Проёб» задана. Сделайте бота админом группы."), 8)
    from .panel import main_menu
    return await main_menu(ctx, r)


@screen("sgno", "owner")
async def skip_group(ctx, r: Req):
    await ctx.notifier.resolve(f"grp:{r.args[0]}")
    try:
        await ctx.bot.delete_message(r.chat_id, r.message.message_id)
    except Exception:
        pass
    return None
