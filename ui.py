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
WAIT: dict[int, dict] = {}             # user_id -> {"act", "data", "back"}
HIST: dict[int, list] = {}             # user_id -> [{"data", "text", "markup", "safe", "ask"}]
STORE = None                           # Database: panel xabari id si qayta ishga tushganda ham esda qolsin
_bg: set = set()


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


class Rich(str):
    """Ekran matni + rasm-kartochka (bloklar). Rasm o'chiq bo'lsa yoki chizilmasa — oddiy matn ko'rinadi."""
    card: list | None = None
    caption: str = ""


def rich(text: str, blocks: list | None, caption: str = "") -> str:
    t = Rich(text)
    t.card = blocks
    t.caption = caption
    return t


def plain_len(text: str) -> int:
    """Telegram'da ko'rinadigan uzunlik (HTML teglarsiz) — rasm ostidagi matn 1024 dan oshmasin."""
    import re
    return len(html.unescape(re.sub(r"<[^>]+>", "", text or "")))


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
            text, data = item[0], item[1]
            extra = {"style": item[2]} if len(item) > 2 and item[2] else {}   # «success» yashil, «danger» qizil
            if data.startswith("http"):
                line.append(InlineKeyboardButton(text=text, url=data, **extra))
            else:
                line.append(InlineKeyboardButton(text=text, callback_data=data[:64], **extra))
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
    return r.L("🟢 yoq", "🟢 вкл") if v else r.L("⚪ o'ch", "⚪ выкл")


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


def panel_kind(chat_id: int) -> str:
    if chat_id in KIND:
        return KIND[chat_id]
    v = (STORE.get(f"panelkind:{chat_id}") if STORE is not None else None) or "text"
    KIND[chat_id] = v
    return v


def _remember(chat_id: int, mid: int, kind: str = "text") -> None:
    PANEL[chat_id] = mid
    KIND[chat_id] = kind
    if STORE is not None:
        if STORE.get(f"panel:{chat_id}") != str(mid):
            STORE.set(f"panel:{chat_id}", str(mid))
        if STORE.get(f"panelkind:{chat_id}") != kind:
            STORE.set(f"panelkind:{chat_id}", kind)


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


# ───────────────────────── rasm-panel
KIND: dict[int, str] = {}              # chat_id -> "text" | "photo"
PHOTO_IDS: dict[str, str] = {}         # kartochka kaliti -> Telegram file_id (bir xil rasm qayta yuklanmaydi)


def _card_key(blocks, theme: str) -> str:
    import hashlib
    return hashlib.sha1((theme + repr(blocks)).encode()).hexdigest()


async def _card_media(blocks, theme: str):
    """-> (media, key): avval yuklangan bo'lsa file_id, aks holda chizilgan JPEG."""
    from aiogram.types import BufferedInputFile
    key = _card_key(blocks, theme)
    if key in PHOTO_IDS:
        return PHOTO_IDS[key], key
    from . import cards
    data = await asyncio.to_thread(cards.render, blocks, theme)
    return BufferedInputFile(data, filename="panel.jpg"), key


def _keep_id(key: str, msg) -> None:
    photos = getattr(msg, "photo", None)
    if key and photos:
        if len(PHOTO_IDS) > 300:
            PHOTO_IDS.clear()
        PHOTO_IDS[key] = photos[-1].file_id


def _look(chat_id: int, text) -> tuple:
    """-> (blocks|None, theme, buttons_styled) — shu chat egasining tanlovi bo'yicha."""
    from . import look
    blocks = getattr(text, "card", None)
    if STORE is None:
        return None, look.DEFAULT_THEME, False
    if blocks and not look.cards_on(STORE, chat_id):
        blocks = None
    return blocks, look.theme_of(STORE, chat_id), look.buttons_on(STORE, chat_id)


async def show(bot, chat_id: int, text: str, markup=None, edit_id: int | None = None, fresh: bool = False,
               styled: bool = False) -> None:
    """Panelni joyida yangilash. fresh=True — panelni pastga (yangi xabar) ko'chirish. Chatda doim bitta panel.

    styled=True — admin paneli: rasm-kartochka (bo'lsa) va tugma uslubi shu adminning tanlovi bo'yicha.
    Matnli xabar rasmga (yoki aksincha) aylana olmaydi — unda yangisi yuboriladi, eskisi o'chadi."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InputMediaPhoto, LinkPreviewOptions
    blocks, theme, btn = _look(chat_id, text) if styled else (None, "", False)
    if btn and markup is not None:
        from . import look
        markup = look.style_markup(markup)
    media = key = None
    if blocks:
        try:
            media, key = await _card_media(blocks, theme)
        except Exception:
            log.exception("Kartochka chizilmadi — matn ko'rsatiladi")
            media = None
    kind = "photo" if media is not None else "text"
    caption = (getattr(text, "caption", "") or None) if kind == "photo" else None
    kw = dict(reply_markup=markup, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
    old = panel_id(chat_id)
    target = edit_id or (None if fresh else old)
    if target:
        cur = panel_kind(chat_id) if target == old else "text"
        ok = False
        if cur == kind:
            try:
                if kind == "text":
                    await bot.edit_message_text(text, chat_id=chat_id, message_id=target, **kw)
                else:
                    msg = await bot.edit_message_media(
                        media=InputMediaPhoto(media=media, caption=caption, parse_mode="HTML"),
                        chat_id=chat_id, message_id=target, reply_markup=markup)
                    _keep_id(key, msg)
                ok = True
            except TelegramBadRequest as exc:
                ok = "not modified" in str(exc).lower()
                if ok and kind == "photo":               # rasm bir xil — tugmalar baribir yangilansin
                    try:
                        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=target, reply_markup=markup)
                    except Exception:
                        pass
            except Exception:
                ok = False
        if ok:
            _remember(chat_id, target, kind)
            if old and old != target:
                await _drop(bot, chat_id, old)           # boshqa xabar panelga aylandi — eski panel ketadi
            return
    if kind == "photo":
        try:
            sent = await bot.send_photo(chat_id, media, caption=caption, parse_mode="HTML", reply_markup=markup)
            _keep_id(key, sent)
        except Exception:
            log.exception("Rasm-panel yuborilmadi — matn yuboriladi")
            kind = "text"
            sent = await bot.send_message(chat_id, text, **kw)
    else:
        sent = await bot.send_message(chat_id, text, **kw)
    _remember(chat_id, sent.message_id, kind)
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
