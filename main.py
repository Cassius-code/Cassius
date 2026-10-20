"""Kirish nuqtasi: bot (panel va «Проёб» guruhi), asosiy akkaunt (kuzatuv), Push akkauntlar va fon ishlari.

Har bir qism alohida vazifa: yiqilsa o'zi qayta ishga tushadi, egasiga bir marta xabar boradi.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from zoneinfo import ZoneInfo

from .config import ConfigError, load_config

log = logging.getLogger("main")


async def supervise(name: str, factory, notifier) -> None:
    delay = 3
    while True:
        started = time.monotonic()
        try:
            await factory()
            log.warning("%s to'xtadi — qayta ishga tushiraman", name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("%s yiqildi", name)
            from .context import tr
            ru_name = {"Telegram bot": "Telegram-бот", "Asosiy akkaunt": "Основной аккаунт", "Nazorat": "Контроль"}
            err = type(exc).__name__
            await notifier.notify_owner(lambda: (tr(f"⚠️ «{name}» xatoga uchradi ({err}) — o'zi qayta ishga tushadi.",
                                                    f"⚠️ «{ru_name.get(name, name)}»: сбой ({err}) — перезапустится сам."),
                                                 None), key=f"crash-{name}", min_interval=900)
        if time.monotonic() - started > 120:
            delay = 3
        await asyncio.sleep(delay)
        delay = min(delay * 2, 120)


class ConflictWatch(logging.Handler):
    """Shu token bilan ikkinchi bot ham ishlayapti (Railway'da ikkita servis / eski deploy) — Telegram xabarlarni
    ikkalasiga bo'lib beradi: tugma bir botda, yozilgan raqam boshqasida. Egaga darhol aytiladi."""

    def __init__(self, notifier):
        super().__init__(logging.ERROR)
        self.notifier = notifier

    def emit(self, record):
        try:
            if "TelegramConflictError" not in record.getMessage():
                return
            from .context import tr
            from .panel_settings import server_name
            me = server_name()
            asyncio.get_running_loop().create_task(self.notifier.notify_owner(lambda: (tr(
                "⚠️ Bot ikki joyda ishlayapti: shu token bilan ikkinchi nusxa bor (Railway'da ikkinchi servis yoki "
                f"eski deploy). Bu xabar «{me}» nusxasidan. Ikkinchisini o'chiring — aks holda yozganlaringiz "
                "yo'qolib qoladi.",
                "⚠️ Бот запущен дважды: с этим токеном работает вторая копия (второй сервис в Railway или старый "
                f"деплой). Это сообщение от копии «{me}». Остановите вторую — иначе ваши сообщения теряются."),
                None), key="conflict", min_interval=1800))
        except Exception:
            pass


async def polling(bot, dp) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=False)


def migrate_old(cfg, db, now: int) -> str:
    """Eski botlarning bazasi shu Volume'da bo'lsa — bir marta ko'chiriladi:
    zaderjka boti (/data/tgcontrol.sqlite3) va kassa boti (Railway'da DB_PATH berilgan bo'lsa)."""
    from .migrate import detect, import_kassa, import_old
    notes = []
    if not db.get("old_imported") and cfg.old_db.exists():
        try:
            st = import_old(db, cfg.old_db, now)
            notes.append("📦 Eski botdan ko'chirildi: " + ", ".join(f"{k} {v}" for k, v in st.items()))
        except Exception as exc:
            log.exception("Eski bazani ko'chirish")
            db.set("old_imported", "error")
            notes.append(f"⚠️ Eski bot ma'lumoti ko'chmadi: {type(exc).__name__}")
    kassa_path = os.environ.get("DB_PATH", "")
    if kassa_path and not db.get("kassa_imported") and os.path.isfile(kassa_path) and detect(kassa_path) == "kassa":
        try:
            st = import_kassa(db, kassa_path)
            notes.append("💵 Kassa ko'chirildi: " + ", ".join(f"{k} {v}" for k, v in st.items()))
        except Exception as exc:
            log.exception("Kassa bazasini ko'chirish")
            notes.append(f"⚠️ Kassa ma'lumoti ko'chmadi: {type(exc).__name__}")
    return "\n".join(notes)


async def amain() -> None:
    cfg = load_config()
    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    from aiogram import Bot, Dispatcher

    from . import group, panel
    from .accounts import AccountPool
    from .attendance import Attendance
    from .context import Ctx
    from .db import Database
    from .notifier import Notifier
    from .push import Pusher
    from .rules import Tracker
    from .services import Scheduler, first_run
    from .userbot import Userbot

    tz = ZoneInfo(cfg.tz_name)
    db = Database(cfg.db_path)
    now = int(time.time())
    note_old = migrate_old(cfg, db, now)
    first_run(db, now, tz)
    db.run("UPDATE broadcasts SET status='interrupted', finished_ts=? WHERE status='running'", (now,))

    bot = Bot(cfg.bot_token)
    me = await bot.get_me()
    log.info("Bot @%s ishga tushdi, baza: %s", me.username, cfg.db_path)

    notifier = Notifier(bot, db, cfg.owner_ids)
    tracker = Tracker(db, tz, notifier)
    att = Attendance(db, tz, notifier)
    userbot = Userbot(cfg, db, tracker, notifier, tz)
    pool = AccountPool(cfg, db, notifier, on_identified=userbot.reload_ids)
    pusher = Pusher(db, tz, notifier, pool, tracker)
    ctx = Ctx(cfg=cfg, db=db, tz=tz, bot=bot, notifier=notifier, tracker=tracker, att=att, userbot=userbot,
              pool=pool, pusher=pusher)

    watch = ConflictWatch(notifier)
    logging.getLogger("aiogram.dispatcher").addHandler(watch)
    dp = Dispatcher()
    dp.include_router(group.build_router(ctx))
    dp.include_router(panel.build_router(ctx))
    await panel.set_commands(ctx)
    pool.sync()

    # yangi xabar emas: egalardagi panel joyida yangilanadi (holat 🟢/🔴 panelning o'zida ko'rinadi)
    await panel.refresh_panels(ctx, note_old)

    sched = Scheduler(ctx)
    tasks = [asyncio.create_task(supervise("Telegram bot", lambda: polling(bot, dp), notifier)),
             asyncio.create_task(supervise("Asosiy akkaunt", userbot.run, notifier)),
             asyncio.create_task(supervise("Nazorat", sched.run, notifier))]

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()
    log.info("To'xtayapman…")
    pusher.stop()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    try:
        await pool.stop()
        await userbot._disconnect()
        await bot.session.close()
    finally:
        logging.getLogger("aiogram.dispatcher").removeHandler(watch)
        db.close()


def main() -> None:
    try:
        asyncio.run(amain())
    except ConfigError as exc:
        print(f"Sozlama xatosi: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
