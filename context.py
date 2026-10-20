"""Hamma servislar bitta joyda (panel va guruh shu orqali ishlaydi)."""
from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


# Bir nechta adminga xabar: har biriga o'z tilida qurish uchun (notifier shu yerga qo'yadi)
LANG: contextvars.ContextVar = contextvars.ContextVar("lang_override", default=None)


def tr(uz: str, ru: str) -> str:
    """Bildirishnoma matni: notifier har oluvchi uchun LANG ni qo'yadi."""
    return ru if (LANG.get() or "uz") == "ru" else uz


def user_lang(db, uid: int | None) -> str:
    if uid:
        v = db.get(f"lang:{uid}")
        if v in ("uz", "ru"):
            return v
    return db.get("lang") or "uz"


@dataclass
class Ctx:
    cfg: object
    db: object
    tz: ZoneInfo
    bot: object
    notifier: object
    tracker: object
    att: object
    userbot: object = None
    pool: object = None
    pusher: object = None
    clock: object = time.time
    login: dict = field(default_factory=dict)      # uid -> LoginFlow (akkauntga kirish jarayoni)
    started: float = field(default_factory=time.time)

    def lang(self, uid: int | None = None) -> str:
        """Panel tili: har admin o'zinikini tanlaydi (lang:<id>), bo'lmasa umumiy."""
        if uid is None and LANG.get():
            return LANG.get()
        return user_lang(self.db, uid)
