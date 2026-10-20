"""Panel yadrosi: chatda doim BITTA panel xabari (joyida o'zgaradi), tugma bosilishi bilan darhol javob, ekranlar.

Har bir ekran — funksiya: (ctx, u: Req) -> (matn, klaviatura). Ro'yxatga @screen("prefiks", level) bilan qo'shiladi.
Matn kiritish — @on_input("amal") bilan. Darajalar: view < full < owner.

«‹ Orqaga» — haqiqiy oldingi ekranga (tarix). Oldingi ekran faqat ko'rish bo'lsa — yangilab ochiladi; amal bajargan
bo'lsa (bazaga yozgan, xabar yuborgan) — qayta bajarilmaydi, o'sha paytdagi ko'rinishi qaytadi.
"""
from __future__ import annotations

import asyncio
import functools
import html
import logging
from dataclasses import dataclass, field

from .db import mark_effect

log = logging.getLogger("ui")

LEVELS = {"": 0, "view": 1, "full": 2, "owner": 3}
SCREENS: dict[str, tuple] = {}         # prefiks -> (fn, level)
INPUTS: dict[str, tuple] = {}          # amal -> (fn, level)
PANEL: dict[int, int] = {}             # chat_id -> panel xabari id
WAIT: "_Wait"                          # user_id -> {"act", "data", "back"} — pastda, bazada ham saqlanadi
HIST: dict[int, list] = {}             # user_id -> [{"data", "text", "markup", "safe", "ask"}]
STORE = None                           # Database: panel xabari id si qayta ishga tushganda ham esda qolsin
_bg: set = set()


# ───────────────────────── kiritish holati (bazada ham)
WAIT_TTL = 30 * 60                     # bot qayta ishga tushsa, 30 daqiqagacha bo'lgan kiritish davom etadi


def quiet_store(fn):
    """Xizmat yozuvi (kiritish holati) — «amal bajarildi» deb hisoblanmasin (Orqaga tarixiga ta'sir qilmasin)."""
    from .db import EFFECTS
    token = EFFECTS.set(None)
    try:
        return fn()
    except Exception:
        log.exception("Holatni saqlashda xato")
        return None
    finally:
        EFFECTS.reset(token)


def _enc(v):
    import datetime as _dt
    if isinstance(v, _dt.date):
        return {"__date__": v.isoformat()}
    raise TypeError(type(v).__name__)


def _dec(d: dict):
    import datetime as _dt
    return _dt.date.fromisoformat(d["__date__"]) if set(d) == {"__date__"} else d


class _Wait(dict):
    """Kiritish kutilmoqda: user_id -> holat. Xotirada va bazada (settings «wait:<id>»): bot yangilanib qayta
    ishga tushsa ham, yarim qolgan kiritish (masalan, akkauntga kirish kodi) yo'qolmaydi."""

    @staticmethod
    def _load(uid):
        import json
        import time as _t
        if STORE is None:
            return None
        raw = quiet_store(lambda: STORE.get(f"wait:{uid}"))
        if not raw:
            return None
        try:
            st = json.loads(raw, object_hook=_dec)
        except ValueError:
            return None
        if _t.time() - st.pop("ts", 0) > WAIT_TTL:
            _Wait._drop(uid)
            return None
        return st

    @staticmethod
    def _drop(uid):
        if STORE is None or not quiet_store(lambda: STORE.get(f"wait:{uid}")):
            return

        def go():
            STORE.run("DELETE FROM settings WHERE key=?", (f"wait:{uid}",))
            STORE._cache.pop(f"wait:{uid}", None)
        quiet_store(go)

    def get(self, uid, default=None):
        if dict.__contains__(self, uid):
            return dict.get(self, uid)
        st = self._load(uid)
        if st is not None:
            dict.__setitem__(self, uid, st)
            return st
        return default

    def __contains__(self, uid):
        return self.get(uid) is not None

    def __getitem__(self, uid):
        v = self.get(uid)
        if v is None:
            raise KeyError(uid)
        return v

    def __setitem__(self, uid, st):
        import json
        import time as _t
        dict.__setitem__(self, uid, st)
        if STORE is not None:
            try:
                raw = json.dumps(dict(st, ts=int(_t.time())), default=_enc, ensure_ascii=False)
            except TypeError:
                self._drop(uid)                      # saqlab bo'lmaydigan ma'lumot — faqat xotirada
                return
            quiet_store(lambda: STORE.set(f"wait:{uid}", raw))

    def pop(self, uid, default=None):
        v = dict.pop(self, uid, None)
        self._drop(uid)
        return default if v is None else v


WAIT = _Wait()


def screen(prefix: str, level: str = "view"):
    def deco(fn):
        @functools.wraps(fn)
        async def wrapped(ctx, r, *a, **kw):
            r.view = prefix + ("".join(":" + str(x) for x in r.args) if r.args else "")
            r.calls += 1
            return await fn(ctx, r, *a, **kw)
        SCREENS[prefix] = (wrapped, level)
        return wrapped
    return deco


def view(r: "Req", data: str) -> None:
    """Ekran amal bajargandan keyin o'zini ko'rsatsa — «Orqaga» uchun xavfsiz manzili (amal argumentlarisiz)."""
    r.view = data
    r.view_set = True


def effect() -> None:
    """Bazaga yozmaydigan, lekin tashqariga ta'sir qiladigan amal (Telethon, fon ishi) — Orqaga qayta bajarmasin."""
    mark_effect()


def on_input(act: str, level: str = "full"):
    def deco(fn):
        INPUTS[act] = (fn, level)
        return fn
    return deco


@dataclass
class Req:
    uid: int
    chat_id: int
    level: str
    data: str = ""
    args: list = field(default_factory=list)
    text: str = ""
    message: object = None            # aiogram Message (matn/fayl kiritilganda)
    lang: str = "uz"
    view: str | None = None           # ko'rsatilgan ekranning manzili (Orqaga uchun)
    view_set: bool = False
    calls: int = 0

    def L(self, uz: str, ru: str) -> str:
        return ru if self.lang == "ru" else uz

    def can(self, level: str) -> bool:
        return LEVELS.get(self.level, 0) >= LEVELS[level]

    @property
    def owner(self) -> bool:
        return self.level == "owner"


class Gone(Exception):
    """Yozuv o'chirilgan yoki birlashtirilgan (eski xabardagi tugma bosildi)."""


def must(x):
    if x is None:
        raise Gone()
    return x


def h(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def kb(*rows):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    out = []
    for row in rows:
        if not row:
            continue
        line = []
        for item in row:
            if item is None:
                continue
            text, data = item
            if data.startswith("http"):
                line.append(InlineKeyboardButton(text=text, url=data))
            else:
                line.append(InlineKeyboardButton(text=text, callback_data=data[:64]))
        if line:
            out.append(line)
    return InlineKeyboardMarkup(inline_keyboard=out)


def grid(items: list, cols: int = 2) -> list[list]:
    return [items[i:i + cols] for i in range(0, len(items), cols)]


def back_data(back: str) -> str:
    """«‹ Orqaga»: tarixdagi oldingi ekran; tarix bo'lmasa (bot qayta ishga tushgan) — back."""
    d = "bk:" + back
    return d if len(d.encode()) <= 64 else "bk"


def nav(r: Req, back: str | None = "m") -> list:
    if back is None or back == "m":
        return [(r.L("⌂ Menyu", "⌂ Меню"), "m")]
    return [(r.L("‹ Orqaga", "‹ Назад"), back_data(back)), (r.L("⌂ Menyu", "⌂ Меню"), "m")]


def onoff(r: Req, v) -> str:
    return r.L("🟢 yoniq", "🟢 вкл") if v else r.L("⚪ o'chiq", "⚪ выкл")


def title(icon: str, text: str, sub: str = "") -> str:
    return f"<b>{icon} {text}</b>" + (f"\n<i>{sub}</i>" if sub else "")


def card(lines: list[str]) -> str:
    lines = [x for x in lines if x is not None]
    return "<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else ""


def join(*parts) -> str:
    return "\n".join(p for p in parts if p)


def bg(coro) -> None:
    """Og'ir ishni fonda bajarish (panel kutib qolmasin)."""
    mark_effect()
    task = asyncio.create_task(coro)
    _bg.add(task)
    task.add_done_callback(_bg.discard)


# ───────────────────────── ko'rsatish
def panel_id(chat_id: int) -> int | None:
    if chat_id in PANEL:
        return PANEL[chat_id]
    if STORE is not None:
        try:
            v = int(STORE.get(f"panel:{chat_id}") or 0)
        except ValueError:
            v = 0
        if v:
            PANEL[chat_id] = v
            return v
    return None


def _remember(chat_id: int, mid: int) -> None:
    PANEL[chat_id] = mid
    if STORE is not None and STORE.get(f"panel:{chat_id}") != str(mid):
        STORE.set(f"panel:{chat_id}", str(mid))


async def _drop(bot, chat_id: int, mid: int | None) -> None:
    if not mid:
        return
    try:
        await bot.delete_message(chat_id, mid)
    except Exception:
        try:                                     # 48 soatdan eski — o'chmaydi: hech bo'lmasa tugmalarsiz qolsin
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=mid, reply_markup=None)
        except Exception:
            pass


async def show(bot, chat_id: int, text: str, markup=None, edit_id: int | None = None, fresh: bool = False) -> None:
    """Panelni joyida yangilash. fresh=True — panelni pastga (yangi xabar) ko'chirish. Chatda doim bitta panel."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import LinkPreviewOptions
    kw = dict(reply_markup=markup, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
    old = panel_id(chat_id)
    target = edit_id or (None if fresh else old)
    if target:
        ok = False
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=target, **kw)
            ok = True
        except TelegramBadRequest as exc:
            ok = "not modified" in str(exc).lower()
        except Exception:
            ok = False
        if ok:
            _remember(chat_id, target)
            if old and old != target:
                await _drop(bot, chat_id, old)           # boshqa xabar panelga aylandi — eski panel ketadi
            return
    sent = await bot.send_message(chat_id, text, **kw)
    _remember(chat_id, sent.message_id)
    if old and old != sent.message_id:
        await _drop(bot, chat_id, old)
    if target and target not in (old, sent.message_id):
        await _drop(bot, chat_id, target)


async def toast(bot, chat_id: int, text: str, seconds: float = 4.0) -> None:
    """Qisqa bildirishnoma (panel ostida), bir necha soniyadan keyin o'chadi."""
    try:
        msg = await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception:
        return

    async def later():
        await asyncio.sleep(seconds)
        try:
            await msg.delete()
        except Exception:
            pass
    bg(later())


def ask(r: Req, act: str, back: str, **data) -> None:
    WAIT[r.uid] = {"act": act, "data": data, "back": back}


def cancel_kb(r: Req, back: str):
    return kb([(r.L("✖️ Bekor qilish", "✖️ Отмена"), back_data(back))])


# ───────────────────────── tarix («‹ Orqaga»)
def remember(uid: int, data: str, text: str, markup, safe: bool, ask: bool) -> None:
    st = HIST.setdefault(uid, [])
    if data == "m":
        st.clear()
    if st and st[-1]["ask"]:                     # kiritish so'rovi tarixda qolmaydi
        st.pop()
    for i, e in enumerate(st):                   # avvalgi ekranga qaytildi — undan keyingilar kesiladi
        if e["data"] == data:
            del st[i:]
            break
    st.append({"data": data, "text": text, "markup": markup, "safe": safe, "ask": ask})
    del st[:-40]


def previous(uid: int) -> dict | None:
    st = HIST.get(uid) or []
    if len(st) < 2:
        return None
    st.pop()
    return st[-1]
