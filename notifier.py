"""Bot nomidan yuborish: «Проёб» guruhiga (ruscha, xodimlar uchun) va egalarga/adminlarga shaxsiy xabar."""
from __future__ import annotations

import asyncio
import logging
import time

from . import people as P

log = logging.getLogger("notifier")


class NotConfigured(RuntimeError):
    pass


class Notifier:
    def __init__(self, bot, db, owners: tuple[int, ...]):
        self.bot = bot
        self.db = db
        self.owners = owners
        self._last: dict[str, float] = {}

    def group_id(self) -> int:
        raw = (self.db.get("proyob_group_id") or "").strip()
        if not raw.lstrip("-").isdigit():
            raise NotConfigured("«Проёб» guruhi belgilanmagan")
        return int(raw)

    @staticmethod
    def _done_kb(alert_id):
        if alert_id is None:
            return None
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнено",
                                                                           callback_data=f"al:{alert_id}")]])

    async def _call(self, fn, *args, **kw):
        from aiogram.exceptions import TelegramMigrateToChat, TelegramRetryAfter
        for attempt in range(3):
            try:
                return await fn(*args, **kw)
            except TelegramRetryAfter as exc:
                await asyncio.sleep(min(60, exc.retry_after + 1))
            except TelegramMigrateToChat as exc:              # guruh supergruppaga aylandi — yangi ID
                new_id = int(exc.migrate_to_chat_id)
                if str(kw.get("chat_id")) == self.db.get("proyob_group_id"):
                    self.db.set("proyob_group_id", str(new_id))
                kw["chat_id"] = new_id
        return await fn(*args, **kw)

    async def send_group(self, text: str, done_button=None) -> tuple[int, int]:
        gid = self.group_id()
        msg = await self._call(self.bot.send_message, chat_id=gid, text=text, reply_markup=self._done_kb(done_button),
                               disable_web_page_preview=True)
        return msg.chat.id, msg.message_id

    async def edit_group(self, gid: int, mid: int, text: str, done_button=None) -> None:
        from aiogram.exceptions import TelegramBadRequest
        try:
            await self._call(self.bot.edit_message_text, chat_id=gid, message_id=mid, text=text,
                             reply_markup=self._done_kb(done_button), disable_web_page_preview=True)
        except TelegramBadRequest as exc:
            if "not modified" not in str(exc).lower():
                raise

    def staff_ids(self, include_view: bool = False) -> list[int]:
        ids = list(self.owners)
        levels = ("owner", "full", "view") if include_view else ("owner", "full")
        for a in P.admins(self.db):
            if a["level"] in levels and a["user_id"] not in ids:
                ids.append(a["user_id"])
        return ids

    def owner_ids(self) -> list[int]:
        ids = list(self.owners)
        for a in P.admins(self.db):
            if a["level"] == "owner" and a["user_id"] not in ids:
                ids.append(a["user_id"])
        return ids

    async def _send_many(self, ids, text, kb=None, key: str = "", min_interval: int = 0, html: bool = True):
        now = time.time()
        if key and min_interval and now - self._last.get(key, 0) < min_interval:
            return []
        if key:
            self._last[key] = now
        out = []
        for uid in ids:
            try:
                out.append(await self._call(self.bot.send_message, chat_id=uid, text=text, reply_markup=kb,
                                            parse_mode="HTML" if html else None, disable_web_page_preview=True))
            except Exception as exc:
                log.info("Xabar yuborilmadi %s: %s", uid, exc)
        return out

    async def notify_owner(self, text: str, kb=None, key: str = "", min_interval: int = 0, html: bool = True):
        return await self._send_many(self.owner_ids(), text, kb, key, min_interval, html)

    async def notify_staff(self, text: str, kb=None, key: str = "", min_interval: int = 0, html: bool = True):
        return await self._send_many(self.staff_ids(), text, kb, key, min_interval, html)

    async def send_document(self, uid: int, data: bytes, filename: str, caption: str = "") -> None:
        from aiogram.types import BufferedInputFile
        await self._call(self.bot.send_document, chat_id=uid, document=BufferedInputFile(data, filename),
                         caption=caption[:1000] or None)
