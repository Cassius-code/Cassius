"""Hamma servislar bitta joyda (panel va guruh shu orqali ishlaydi)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


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

    def lang(self) -> str:
        return self.db.get("lang") or "uz"
