"""Panel yadrosi: bitta xabar joyida o'zgaradi (chat toza), tugma bosilishi bilan darhol javob, ekranlar ro'yxati.

Har bir ekran — funksiya: (ctx, u: Req) -> (matn, klaviatura). Ro'yxatga @screen("prefiks", level) bilan qo'shiladi.
Matn kiritish — @on_input("amal") bilan. Darajalar: view < full < owner.
"""
from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass, field

log = logging.getLogger("ui")

LEVELS = {"": 0, "view": 1, "full": 2, "owner": 3}
SCREENS: dict[str, tuple] = {}         # prefiks -> (fn, level)
INPUTS: dict[str, tuple] = {}          # amal -> (fn, level)
PANEL: dict[int, int] = {}             # chat_id -> panel xabari id
WAIT: dict[int, dict] = {}             # user_id -> {"act", "data", "back"}
_bg: set = set()


def screen(prefix: str, level: str = "view"):
    def deco(fn):
        SCREENS[prefix] = (fn, level)
        return fn
    return deco


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


def nav(r: Req, back: str | None = "m") -> list:
    if back is None or back == "m":
        return [(r.L("⌂ Menyu", "⌂ Меню"), "m")]
    return [(r.L("‹ Orqaga", "‹ Назад"), back), (r.L("⌂ Menyu", "⌂ Меню"), "m")]


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
    task = asyncio.create_task(coro)
    _bg.add(task)
    task.add_done_callback(_bg.discard)


# ───────────────────────── ko'rsatish
async def show(bot, chat_id: int, text: str, markup=None, edit_id: int | None = None, fresh: bool = False) -> None:
    """Panelni joyida yangilash. fresh=True — panelni pastga (yangi xabar) ko'chirish."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import LinkPreviewOptions
    kw = dict(reply_markup=markup, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
    target = edit_id or (None if fresh else PANEL.get(chat_id))
    if target:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=target, **kw)
            PANEL[chat_id] = target
            return
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                PANEL[chat_id] = target
                return
        except Exception:
            pass
    old = PANEL.get(chat_id)
    sent = await bot.send_message(chat_id, text, **kw)
    PANEL[chat_id] = sent.message_id
    if old and old != sent.message_id:
        try:
            await bot.delete_message(chat_id, old)
        except Exception:
            pass


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
    return kb([(r.L("✖️ Bekor qilish", "✖️ Отмена"), back)])
