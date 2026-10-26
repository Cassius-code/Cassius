"""Telegram akkauntlari (Telethon): ulanish sikli, qayta ulanish, kirish (login) — asosiy akkaunt va Push akkauntlari
uchun umumiy asos."""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger("tg")


class LoginFlow:
    """Akkauntga bot chatidan kirish (iPhone'da terminal yo'q)."""

    def __init__(self, api_id: int, api_hash: str):
        self.api_id, self.api_hash = api_id, api_hash
        self.client = None
        self.phone = ""
        self.code_hash = ""

    async def start(self, phone: str) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        await self.cancel()
        self.client = TelegramClient(StringSession(), self.api_id, self.api_hash)
        await self.client.connect()
        self.phone = phone
        sent = await self.client.send_code_request(phone)
        self.code_hash = sent.phone_code_hash

    def state(self) -> dict:
        """Bot qayta ishga tushsa ham kirishni davom ettirish uchun (seans kaliti, raqam, kod xeshi)."""
        return {"s": self.client.session.save() if self.client else "", "phone": self.phone, "hash": self.code_hash}

    @classmethod
    async def resume(cls, api_id: int, api_hash: str, st: dict) -> "LoginFlow":
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        flow = cls(api_id, api_hash)
        flow.client = TelegramClient(StringSession(st.get("s") or ""), api_id, api_hash)
        await flow.client.connect()
        flow.phone, flow.code_hash = st.get("phone", ""), st.get("hash", "")
        return flow

    async def submit_code(self, code: str) -> str:
        """'ok' — kirildi, 'password' — ikki bosqichli parol kerak."""
        from telethon import errors
        try:
            await self.client.sign_in(phone=self.phone, code=code, phone_code_hash=self.code_hash)
        except errors.SessionPasswordNeededError:
            return "password"
        return "ok"

    async def submit_password(self, password: str) -> None:
        await self.client.sign_in(password=password)

    def session_string(self) -> str:
        return self.client.session.save()

    async def cancel(self) -> None:
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None


def me_label(me) -> str:
    name = " ".join(x for x in (getattr(me, "first_name", "") or "", getattr(me, "last_name", "") or "") if x)
    user = f"@{me.username}" if getattr(me, "username", None) else ""
    return " ".join(x for x in (name, user) if x) or str(getattr(me, "id", ""))


class TgAccount:
    """Bitta Telegram akkaunti: ulanadi, uzilsa qayta ulanadi, sessiya almashsa qayta ishga tushadi."""

    def __init__(self, cfg, db, notifier):
        self.cfg, self.db, self.notifier = cfg, db, notifier
        self.client = None
        self.state = "starting"       # starting|disabled|no_session|connecting|online|offline|unauthorized
        self.me_id: int | None = None
        self.me_label = ""
        self.tick = 15                # davriy ish (periodic) shu soniyada bir chaqiriladi
        self._wake = asyncio.Event()

    # ---- voris klasslar belgilaydi
    def session(self) -> str:
        return ""

    def title(self) -> str:
        return "akkaunt"

    async def on_online(self, client) -> None:
        """Ulangandan keyin (hodisalar, sinxron)."""

    async def periodic(self, client) -> None:
        """Har 15 soniyada (sinxron va h.k.)."""

    # ---- umumiy
    def wake(self) -> None:
        self._wake.set()

    async def _sleep_or_wake(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        self._wake.clear()

    async def _disconnect(self) -> None:
        client, self.client = self.client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    def _new_client(self, session: str):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(session), self.cfg.api_id, self.cfg.api_hash, connection_retries=-1,
                              retry_delay=2, auto_reconnect=True, request_retries=5,
                              flood_sleep_threshold=getattr(self, "flood_threshold", 60))

    async def run(self) -> None:
        backoff = 5
        while True:
            if not (self.cfg.api_id and self.cfg.api_hash):
                self.state = "disabled"
                await self._sleep_or_wake(60)
                continue
            session = self.session()
            if not session:
                self.state = "no_session"
                await self._sleep_or_wake(60)
                continue
            try:
                started = time.monotonic()
                await self._serve(session)
                await self._disconnect()
                if time.monotonic() - started > 120:
                    backoff = 5
            except asyncio.CancelledError:
                await self._disconnect()
                raise
            except Exception as exc:
                self.state = "offline"
                log.exception("%s: ulanish xatosi", self.title())
                from .context import tr
                ttl, err = self.title(), type(exc).__name__
                await self.notifier.notify_owner(
                    lambda: (tr(f"⚠️ {ttl}: uzildi ({err}). Qayta ulanyapman.",
                                f"⚠️ {ttl.replace('Asosiy akkaunt', 'Основной аккаунт').replace('Push «', 'Пуш «')}: связь потеряна ({err}). "
                                "Переподключаюсь."), None), key=f"down-{self.title()}", min_interval=1800)
                await self._disconnect()
                await self._sleep_or_wake(backoff)
                backoff = min(backoff * 2, 300)

    async def _serve(self, session: str) -> None:
        from telethon import errors
        self.state = "connecting"
        client = self._new_client(session)
        self.client = client
        await client.connect()
        if not await client.is_user_authorized():
            self.state = "unauthorized"
            from .context import tr
            ttl = self.title()
            await self.notifier.notify_owner(lambda: (tr(
                f"🔑 {ttl}: seans yaroqsiz — ⚙️ Sozlamalar → akkauntlar orqali qaytadan ulang.",
                f"🔑 {ttl.replace('Asosiy akkaunt', 'Основной аккаунт').replace('Push «', 'Пуш «')}: сессия недействительна — войдите заново: "
                "⚙️ Настройки → аккаунты."), None), key=f"unauth-{self.title()}", min_interval=3600)
            await self._disconnect()
            await self._sleep_or_wake(300)
            return
        me = await client.get_me()
        self.me_id, self.me_label = int(me.id), me_label(me)
        self.state = "online"
        for k in (f"down-{self.title()}", f"unauth-{self.title()}"):     # ulandi — eski ogohlantirish chatdan ketadi
            try:
                await self.notifier.resolve(k)
            except Exception:
                pass
        await self.on_online(client)
        failures, last_ping = 0, time.monotonic()
        while True:
            await self._sleep_or_wake(self.tick)
            if self.client is not client or self.session() != session:
                return
            if time.monotonic() - last_ping >= 60:
                last_ping = time.monotonic()
                try:
                    await asyncio.wait_for(client.get_me(), timeout=30)
                    failures, self.state = 0, "online"
                except getattr(errors, "AuthKeyError", ()):
                    raise
                except Exception as exc:
                    failures += 1
                    if failures >= 3:
                        raise ConnectionError("Telegram javob bermadi") from exc
            try:
                await self.periodic(client)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s: davriy ish xatosi", self.title())
