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


BANNED = ("UserDeactivatedBanError", "UserDeactivatedError", "PhoneNumberBannedError")
CONNECT_TIMEOUT = 45           # ulanish shuncha soniyada bo'lmasa — keyinroq yana (cheksiz «ulanmoqda» emas)


class SessionDead(RuntimeError):
    """Seans yaroqsiz (chiqib ketilgan / o'chirilgan) — qayta kirish kerak, qayta urinilmaydi."""


def classify_error(exc) -> str:
    """Ulanish xatosi qaysi turda: server — Telegram/tarmoq vaqtincha (o'zi ulanadi); session — seans o'chgan
    (🔑 qayta kirish); banned — akkaunt bloklangan (boshqa akkaunt kerak)."""
    names = {c.__name__ for c in type(exc).__mro__}
    if names & set(BANNED):
        return "banned"
    if isinstance(exc, SessionDead) or names & {"UnauthorizedError", "AuthKeyError"}:
        return "session"
    return "server"


class TgAccount:
    """Bitta Telegram akkaunti: ulanadi, uzilsa qayta ulanadi, sessiya almashsa qayta ishga tushadi.
    Sabab aniq: server (o'zi ulanadi — egaga N daqiqadan keyin bitta xabar, ulanganda o'chadi), session (seans o'chgan —
    darhol 🔑 Qayta kirish tugmasi bilan; qayta urinilmaydi), banned (bloklangan — boshqa akkaunt ulang)."""

    DOWN_NOTIFY = 180             # shuncha soniya ulanmasa — egaga xabar (asosiy akkaunt: 3 daqiqa)

    def __init__(self, cfg, db, notifier):
        self.cfg, self.db, self.notifier = cfg, db, notifier
        self.client = None
        self.state = "starting"       # starting|disabled|no_session|connecting|online|offline|unauthorized|banned
        self.reason = ""              # '' | server | session | banned
        self.error = ""               # oxirgi xato nomi (panelda)
        self.down_since: float | None = None
        self.retry_at: float | None = None
        self._dead: str | None = None  # yaroqsiz deb topilgan seans (o'zgarmaguncha qayta urinilmaydi)
        self._down_sent = False
        self.me_id: int | None = None
        self.me_label = ""
        self.tick = 15                # davriy ish (periodic) shu soniyada bir chaqiriladi
        self._wake = asyncio.Event()

    # ---- voris klasslar belgilaydi
    def session(self) -> str:
        return ""

    def title(self) -> str:
        return "akkaunt"

    def key(self) -> str:
        """Ogohlantirish kaliti (nomi o'zgarsa ham bir xil)."""
        return self.title()

    def relogin_data(self) -> str:
        """🔑 Qayta kirish tugmasi qayerga."""
        return "sml:main"

    def accounts_data(self) -> str:
        return "sm"

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
                await asyncio.wait_for(client.disconnect(), timeout=10)
            except Exception:
                pass

    def _new_client(self, session: str):
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        return TelegramClient(StringSession(session), self.cfg.api_id, self.cfg.api_hash, connection_retries=3,
                              retry_delay=3, timeout=15, auto_reconnect=True, request_retries=3,
                              flood_sleep_threshold=getattr(self, "flood_threshold", 60))

    def _names(self) -> tuple[str, str]:
        ttl = self.title()
        return ttl, ttl.replace("Asosiy akkaunt", "Основной аккаунт").replace("Push «", "Пуш «")

    async def _online_clear(self) -> None:
        """Ulandi — eski ogohlantirishlar chatdan o'chadi."""
        self.reason, self.error, self.down_since, self.retry_at, self._down_sent = "", "", None, None, False
        for k in (f"down-{self.key()}", f"unauth-{self.key()}", f"down-{self.title()}", f"unauth-{self.title()}"):
            try:
                await self.notifier.resolve(k)
            except Exception:
                pass

    async def _notify_down(self) -> None:
        """Telegram serveri N daqiqadan beri javob bermayapti — bitta xabar (ulanganda o'chadi)."""
        if self._down_sent or self.down_since is None or time.time() - self.down_since < self.DOWN_NOTIFY:
            return
        self._down_sent = True
        from .context import tr
        uz, ru = self._names()
        mins = max(1, int(time.time() - self.down_since) // 60)
        await self.notifier.notify_owner(lambda: (tr(
            f"⚠️ {uz}: Telegram serveri javob bermayapti ({mins} daqiqadan beri). Hech narsa qilmang — o'zi ulanadi. "
            "Ulanganda bu xabar o'chadi.",
            f"⚠️ {ru}: сервер Telegram не отвечает (уже {mins} мин). Ничего не делайте — подключится сам. "
            "Когда подключится, это сообщение исчезнет."), None), key=f"down-{self.key()}")

    async def _notify_dead(self, kind: str) -> None:
        """Seans o'chgan yoki akkaunt bloklangan — darhol, tugma bilan (bir marta)."""
        from .context import tr
        from .ui import kb
        uz, ru = self._names()
        if kind == "banned":
            def build():
                return (tr(f"⛔ {uz}: akkaunt Telegram tomonidan bloklangan. Bot unga qayta urinmaydi — boshqa akkaunt "
                           "ulang.",
                           f"⛔ {ru}: аккаунт заблокирован Telegram. Бот больше не пытается — подключите другой "
                           "аккаунт."),
                        kb([(tr("📲 Akkauntlar", "📲 Аккаунты"), self.accounts_data())]))
        else:
            def build():
                return (tr(f"🔑 {uz}: seans o'chgan (akkauntdan chiqilgan yoki boshqa qurilmada o'chirilgan). "
                           "Qayta kiring — papkasi va sozlamalari saqlanadi.",
                           f"🔑 {ru}: сессия завершена (вышли из аккаунта или завершили на другом устройстве). "
                           "Войдите заново — папка и настройки сохранятся."),
                        kb([(tr("🔑 Qayta kirish", "🔑 Войти заново"), self.relogin_data())]))
        await self.notifier.notify_owner(build, key=f"unauth-{self.key()}")

    async def run(self) -> None:
        backoff = 5
        while True:
            if not (self.cfg.api_id and self.cfg.api_hash):
                self.state = "disabled"
                await self._sleep_or_wake(60)
                continue
            session = self.session()
            if not session:
                self.state, self.reason = "no_session", ""
                await self._sleep_or_wake(60)
                continue
            if session == self._dead:                      # yaroqsiz seans — yangisi kelguncha kutamiz
                await self._sleep_or_wake(300)
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
                await self._disconnect()
                kind = classify_error(exc)
                self.error = type(exc).__name__
                if kind in ("session", "banned"):
                    self._dead = session
                    self.state = "banned" if kind == "banned" else "unauthorized"
                    self.reason, self.retry_at = kind, None
                    log.warning("%s: %s (%s) — qayta urinilmaydi", self.title(), kind, self.error)
                    try:
                        await self._notify_dead(kind)
                    except Exception:
                        log.exception("Ogohlantirish yuborilmadi")
                    continue
                self.state, self.reason = "offline", "server"
                if self.down_since is None:
                    self.down_since = time.time()
                    log.warning("%s: Telegram bilan aloqa yo'q (%s) — qayta ulanaman", self.title(), self.error)
                wait = max(backoff, int(getattr(exc, "seconds", 0) or 0))
                self.retry_at = time.time() + wait
                try:
                    await self._notify_down()
                except Exception:
                    log.exception("Ogohlantirish yuborilmadi")
                await self._sleep_or_wake(wait)
                backoff = min(backoff * 2, 120)

    async def _serve(self, session: str) -> None:
        from telethon import errors
        self.state = "connecting"
        client = self._new_client(session)
        self.client = client
        await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
        if not await asyncio.wait_for(client.is_user_authorized(), timeout=30):
            raise SessionDead("unauthorized")
        me = await asyncio.wait_for(client.get_me(), timeout=30)
        if me is None:
            raise SessionDead("no user")
        self.me_id, self.me_label = int(me.id), me_label(me)
        self.state, self._dead = "online", None
        await self._online_clear()
        await self.on_online(client)
        failures, last_ping, gone = 0, time.monotonic(), None
        while True:
            await self._sleep_or_wake(self.tick)
            if self.client is not client or self.session() != session:
                return
            if not client.is_connected():                  # Telethon o'zi qayta ulanadi — 60 s kutamiz
                gone = gone or time.monotonic()
                if time.monotonic() - gone > 60:
                    raise ConnectionError("aloqa uzildi")
                continue
            gone = None
            if time.monotonic() - last_ping >= 60:
                last_ping = time.monotonic()
                try:
                    await asyncio.wait_for(client.get_me(), timeout=30)
                    failures, self.state = 0, "online"
                except (errors.UnauthorizedError, errors.AuthKeyError):
                    raise
                except Exception as exc:
                    failures += 1
                    if failures >= 2:
                        raise ConnectionError("Telegram javob bermadi") from exc
            try:
                await self.periodic(client)
            except asyncio.CancelledError:
                raise
            except (errors.UnauthorizedError, errors.AuthKeyError):
                raise
            except Exception:
                log.exception("%s: davriy ish xatosi", self.title())
