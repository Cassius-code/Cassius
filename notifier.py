"""Bot nomidan yuborish: «Проёб» guruhiga (ruscha, xodimlar uchun) va egalarga/adminlarga shaxsiy xabar."""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re
import time
from collections import deque

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
        self.userbot = None                     # asosiy akkaunt — «Проёб»ga uning nomidan yozish mumkin
        self._own: deque = deque(maxlen=300)    # asosiy akkaunt yozgan matnlar: bot ularni qayta ishlamasin
        self._main_pause = 0.0                  # asosiy akkaunt yoza olmadi — shu vaqtgacha «Проёб»ga bot yozadi

    # ───────────── «Проёб»ga kim nomidan yoziladi: bot yoki asosiy akkaunt (anonim admin bo'lsa — guruh nomidan)
    def _main(self):
        if self.db.get("proyob_sender") != "main" or time.time() < self._main_pause:
            return None
        ub = self.userbot
        if ub is None or ub.state != "online" or ub.client is None:
            return None
        return ub.client

    @staticmethod
    def _norm(text: str) -> str:
        t = _html.unescape(re.sub(r"<[^>]+>", "", text or ""))
        return "\n".join(line.strip() for line in t.strip().splitlines() if line.strip())

    def is_own(self, text: str) -> bool:
        """Bu xabarni bot asosiy akkaunt orqali o'zi yozganmi (guruhdagi yangi xabar sifatida qaytib keladi)."""
        t, now = self._norm(text), time.time()
        return bool(t) and any(x == t and now - ts < 300 for ts, x in self._own)

    @staticmethod
    def main_error(exc) -> tuple[str, int]:
        """Asosiy akkaunt «Проёб»ga yoza olmadi: sabab (flood | spam | access | other) va necha soniya bot yozadi."""
        name = type(exc).__name__
        sec = int(getattr(exc, "seconds", 0) or 0)
        if sec or "FloodWait" in name or "SlowModeWait" in name:
            return "flood", max(sec, 30)
        if name in ("PeerFloodError", "UserBannedInChannelError"):
            return "spam", 3600
        if name in ("ChatWriteForbiddenError", "ChannelPrivateError", "ChatAdminRequiredError",
                    "UserNotParticipantError", "ChatRestrictedError", "ChatGuestSendForbiddenError", "ValueError"):
            return "access", 600
        return "other", 300

    async def _main_failed(self, exc) -> None:
        kind, pause = self.main_error(exc)
        self._main_pause = time.time() + pause
        name = type(exc).__name__
        log.warning("«Проёб»: asosiy akkaunt yoza olmadi (%s) — %s s bot yozadi", name, pause)
        if kind == "flood" and pause < 600:
            return                  # Telegram ozgina kutishni so'radi (ko'p xabar, masalan Push) — oddiy hol, xabar shart emas
        m = max(1, pause // 60)
        texts = {
            "flood": (f"⚠️ Telegram asosiy akkauntni {m} daqiqaga sekinlashtirdi (juda ko'p xabar — masalan Push). "
                      "Bu spam emas. Shu vaqt «Проёб»ga bot o'zi yozadi — xabarlar yo'qolmaydi.",
                      f"⚠️ Telegram замедлил основной аккаунт на {m} мин (слишком много сообщений — например, Пуш). "
                      "Это не спам. Пока в «Проёб» пишет бот — сообщения не теряются."),
            "spam": ("⚠️ Asosiy akkaunt spam-cheklovda — «Проёб»ga yoza olmadi. Hozircha bot o'zi yozyapti. "
                     "Tekshirish: shu akkauntdan @SpamBot ga /start.",
                     "⚠️ Основной аккаунт под спам-ограничением — не может писать в «Проёб». Пока пишет бот. "
                     "Проверка: с этого аккаунта /start в @SpamBot."),
            "access": ("⚠️ Asosiy akkaunt «Проёб»ga yoza olmadi: guruhda yo'q yoki yozishga ruxsat yo'q. "
                       "Hozircha bot o'zi yozyapti.",
                       "⚠️ Основной аккаунт не может писать в «Проёб»: его нет в группе или нет права писать. "
                       "Пока пишет бот."),
            "other": (f"⚠️ Asosiy akkaunt «Проёб»ga yoza olmadi ({name}). Hozircha bot o'zi yozyapti — "
                      "xabarlar yo'qolmaydi.",
                      f"⚠️ Основной аккаунт не смог написать в «Проёб» ({name}). Пока пишет бот — "
                      "сообщения не теряются."),
        }
        uz, ru = texts[kind]
        from .context import tr
        try:
            await self.notify_owner(lambda: (tr(uz, ru), None), key=f"main-proyob-{kind}", min_interval=3600)
        except Exception:
            pass

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
        for attempt in range(2):
            try:
                return await fn(*args, **kw)
            except TelegramRetryAfter as exc:
                if exc.retry_after > 30:
                    raise                                      # uzoq kutish — keyingi urinishda (bot qotib qolmasin)
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramMigrateToChat as exc:              # guruh supergruppaga aylandi — yangi ID
                new_id = int(exc.migrate_to_chat_id)
                if str(kw.get("chat_id")) == self.db.get("proyob_group_id"):
                    self.db.set("proyob_group_id", str(new_id))
                kw["chat_id"] = new_id
        return await fn(*args, **kw)

    def trash(self, gid: int, mid: int, kind: str = "info") -> None:
        """🧹 Bu xabar vaqti kelganda o'chsin (tidy.sweep)."""
        try:
            from .tidy import remember
            remember(self.db, gid, mid, kind, int(time.time()))
        except Exception as exc:
            log.info("Tozalash navbatiga qo'shilmadi: %s", exc)

    async def send_group(self, text: str, done_button=None, reply_to: int | None = None,
                         trash: str | None = None) -> tuple[int, int]:
        """«Проёб»ga xabar. trash="info" — vaqti kelganda o'zi o'chadi (🧹 sozlamasi)."""
        gid, mid = await self._send_group(text, done_button, reply_to)
        if trash:
            self.trash(gid, mid, trash)
        return gid, mid

    async def _send_group(self, text: str, done_button=None, reply_to: int | None = None) -> tuple[int, int]:
        """«Проёб»ga xabar. Asosiy akkaunt nomidan yozish yoqilgan bo'lsa — o'sha akkaunt (tugmasiz: oddiy akkaunt
        tugma qo'sha olmaydi); u yoza olmasa — bot yozadi (xabar yo'qolmaydi)."""
        gid = self.group_id()
        client = self._main()
        if client is not None:
            for attempt in (1, 2):
                try:
                    self._own.append((time.time(), self._norm(text)))
                    m = await client.send_message(gid, text, parse_mode="html", link_preview=False, reply_to=reply_to)
                    return gid, int(m.id)
                except ValueError as exc:                # guruh akkaunt xotirasida yo'q (ishga tushgan zahoti)
                    if attempt == 1:
                        try:
                            async for _d in client.iter_dialogs(limit=300):
                                pass
                            continue
                        except Exception:
                            pass
                    await self._main_failed(exc)
                    break
                except Exception as exc:
                    await self._main_failed(exc)
                    break
        kw = {"reply_to_message_id": reply_to} if reply_to else {}
        msg = await self._call(self.bot.send_message, chat_id=gid, text=text, reply_markup=self._done_kb(done_button),
                               disable_web_page_preview=True, parse_mode="HTML", **kw)
        return msg.chat.id, msg.message_id

    def _main_any(self):
        ub = self.userbot
        return ub.client if ub is not None and ub.state == "online" and ub.client is not None else None

    async def delete_group(self, gid: int, mid: int) -> bool:
        """«Проёб»dagi o'z xabarini o'chirish (bot yoki asosiy akkaunt yozgan). 48 soatdan eskisi — False."""
        try:
            await self._call(self.bot.delete_message, chat_id=gid, message_id=mid)
            return True
        except Exception:
            pass
        client = self._main_any()
        if client is not None:
            try:
                return bool(await client.delete_messages(gid, [mid]))
            except Exception:
                return False
        return False

    async def edit_group(self, gid: int, mid: int, text: str, done_button=None) -> None:
        """Xabarni yozgan o'zi tahrirlaydi: avval hozirgi tanlov (bot yoki asosiy akkaunt), bo'lmasa — ikkinchisi."""
        from aiogram.exceptions import TelegramBadRequest
        order = ("main", "bot") if self._main() is not None else ("bot", "main")
        last = None
        for who in order:
            try:
                if who == "bot":
                    await self._call(self.bot.edit_message_text, chat_id=gid, message_id=mid, text=text,
                                     reply_markup=self._done_kb(done_button), disable_web_page_preview=True,
                                     parse_mode="HTML")
                    return
                client = self._main_any()
                if client is None:
                    continue
                self._own.append((time.time(), self._norm(text)))
                await client.edit_message(gid, mid, text, parse_mode="html", link_preview=False)
                return
            except TelegramBadRequest as exc:
                if "not modified" in str(exc).lower():
                    return
                last = exc
            except Exception as exc:
                if "NotModified" in type(exc).__name__:
                    return
                last = exc
        if last is not None:
            raise last

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
        """key berilsa: shu kalitli eski xabarlar o'chadi (chat toza), yangilari eslab qolinadi — keyin resolve()."""
        now = time.time()
        if key and min_interval and now - self._last.get(key, 0) < min_interval:
            return []
        if key:
            self._last[key] = now
            await self.resolve(key)
        out = []
        from .context import LANG, user_lang
        for uid in ids:
            try:
                t, k = text, kb
                if callable(text):                        # har kimga o'z tilida
                    tok = LANG.set(user_lang(self.db, uid))
                    try:
                        t, k = text()
                    finally:
                        LANG.reset(tok)
                if self.locked(uid):                      # 🔒 panel qulflangan — xabar qulf ochilganda keladi
                    self._hold(uid, key, t, k, html)
                    continue
                msg = await self._call(self.bot.send_message, chat_id=uid, text=t, reply_markup=k,
                                       parse_mode="HTML" if html else None, disable_web_page_preview=True)
                out.append(msg)
                if key:
                    self.db.run("INSERT INTO sent(key, chat_id, msg_id, ts) VALUES(?,?,?,?)",
                                (key, uid, msg.message_id, int(now)))
            except Exception as exc:
                log.info("Xabar yuborilmadi %s: %s", uid, exc)
        return out

    async def send_keyed(self, ids, text: str, kb=None, key: str = "", html: bool = True):
        return await self._send_many(ids, text, kb, key=key, html=html)

    def has_key(self, key: str) -> bool:
        return self.db.one("SELECT 1 FROM sent WHERE key=? LIMIT 1", (key,)) is not None

    async def resolve(self, key: str, text: str | None = None, kb=None, skip: tuple = ()) -> int:
        """Hamma nusxa: text yo'q — o'chiriladi; text bor — shu matnga almashtiriladi (kb bilan yoki tugmasiz).
        skip — (chat_id, msg_id) ro'yxati: bu nusxalarga tegilmaydi (masalan, panelga aylangan xabar)."""
        rows = self.db.all("SELECT chat_id, msg_id FROM sent WHERE key=?", (key,))
        for row in rows:
            if (row["chat_id"], row["msg_id"]) in skip:
                continue
            if text is None:
                try:
                    await self.bot.delete_message(row["chat_id"], row["msg_id"])
                    continue
                except Exception:
                    pass
            try:
                await self.bot.edit_message_text(text or "✅", chat_id=row["chat_id"], message_id=row["msg_id"],
                                                 reply_markup=kb if text else None, parse_mode="HTML",
                                                 disable_web_page_preview=True)
            except Exception:
                pass
        if text is None or kb is None:
            self.db.run("DELETE FROM sent WHERE key=?", (key,))
        if key:                                            # 🔒 qulf paytida kutib turgan nusxalar ham
            if text is None:
                self.db.run("DELETE FROM held WHERE key=?", (key,))
            else:
                self.db.run("UPDATE held SET text=?, kb=? WHERE key=?",
                            (text or "✅", kb.model_dump_json(exclude_none=True) if kb is not None else "", key))
        return len(rows)

    # ───────────── 🔒 panel qulfi: qulflangan egaga xabarlar yuborilmaydi — qulf ochilganda keladi
    def locked(self, uid) -> bool:
        return bool(uid) and self.db.get(f"lock:{uid}") == "1"

    def _hold(self, uid: int, key: str, text: str, kb, html: bool) -> None:
        self.db.run("INSERT INTO held(uid, key, text, kb, html, ts) VALUES(?,?,?,?,?,?)",
                    (uid, key or "", text, kb.model_dump_json(exclude_none=True) if kb is not None else "",
                     1 if html else 0, int(time.time())))

    async def release(self, uid: int) -> int:
        """Qulf ochildi: kutib turgan xabarlar tartib bilan (savollar tugmalari bilan). -> nechta."""
        from aiogram.types import InlineKeyboardMarkup
        n = 0
        for row in self.db.all("SELECT * FROM held WHERE uid=? ORDER BY id", (uid,)):
            self.db.run("DELETE FROM held WHERE id=?", (row["id"],))
            try:
                k = InlineKeyboardMarkup.model_validate_json(row["kb"]) if row["kb"] else None
                msg = await self._call(self.bot.send_message, chat_id=uid, text=row["text"], reply_markup=k,
                                       parse_mode="HTML" if row["html"] else None, disable_web_page_preview=True)
                if row["key"]:
                    self.db.run("INSERT INTO sent(key, chat_id, msg_id, ts) VALUES(?,?,?,?)",
                                (row["key"], uid, msg.message_id, int(time.time())))
                n += 1
            except Exception as exc:
                log.info("Kutib turgan xabar yuborilmadi %s: %s", uid, exc)
        return n

    def forget(self, chat_id: int, msg_id: int) -> None:
        """Xabar panelga aylandi — endi u savol nusxasi emas."""
        self.db.run("DELETE FROM sent WHERE chat_id=? AND msg_id=?", (chat_id, msg_id))

    async def notify_owner(self, text: str, kb=None, key: str = "", min_interval: int = 0, html: bool = True):
        return await self._send_many(self.owner_ids(), text, kb, key, min_interval, html)

    async def notify_staff(self, text: str, kb=None, key: str = "", min_interval: int = 0, html: bool = True):
        return await self._send_many(self.staff_ids(), text, kb, key, min_interval, html)

    async def send_document(self, uid: int, data: bytes, filename: str, caption: str = "") -> None:
        from aiogram.types import BufferedInputFile
        await self._call(self.bot.send_document, chat_id=uid, document=BufferedInputFile(data, filename),
                         caption=caption[:1000] or None)
