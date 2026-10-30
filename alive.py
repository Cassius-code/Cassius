"""🫀 Bot tirikligi (egasi bilan kelishilgan, 2026-10-30).

* Ichki qism (zaderjka nazorati, doska, panel) 5 daqiqa qotib qolsa — egaga xabar; qism qayta ishlasa — o'sha xabar
  «✅ qayta ishlayapti» ga almashadi.
* Bot butunlay o'chib qolsa, o'zi yoza olmaydi: har 30 soniyada «tirikman» vaqti bazaga yoziladi. Qayta yonganda
  5 daqiqadan ko'p to'xtab turgan bo'lsa — «⚠️ Bot 14:05–14:12 orasida to'xtab turdi (7 daq)». Qisqa o'chishlar
  (masalan, GitHub'ga yangi versiya yuklanganda 1–2 daqiqa) uchun xabar yo'q."""
from __future__ import annotations

import asyncio
import logging
import time

from .context import tr
from .timeutil import fmt

log = logging.getLogger("alive")

STALL = 5 * 60                 # shuncha soniya qism ishlamasa (yoki bot o'chib tursa) — egaga xabar
EVERY = 30                     # soniya: tekshiruv va «tirikman» yozuvi
PARTS = {"nazorat": ("Zaderjka nazorati", "Контроль задержек"), "doska": ("📌 Doska", "📌 Доска"),
         "panel": ("Panel", "Панель")}
HEART: dict[str, float] = {}   # qism -> oxirgi marta ishlagan vaqt (monotonic)
_STARTED = time.monotonic()
_down: set[str] = set()


def beat(name: str) -> None:
    HEART[name] = time.monotonic()


async def startup_note(ctx, now: int) -> None:
    """Bot qayta yondi: oldingi «tirikman» vaqtidan beri 5 daqiqadan ko'p o'tgan bo'lsa — egaga xabar."""
    last = ctx.db.get_int("alive_ts")
    ctx.db.set("alive_ts", str(now))
    if not last or now - last < STALL:
        return
    mins = (now - last) // 60
    a, b = fmt(last, ctx.tz, "%d.%m %H:%M"), fmt(now, ctx.tz, "%H:%M")
    await ctx.notifier.notify_owner(lambda: (tr(
        f"⚠️ Bot {a}–{b} orasida to'xtab turdi ({mins} daq). Shu vaqtdagi xabarlarni bot qayta ulanganda o'zi oladi.",
        f"⚠️ Бот не работал {a}–{b} ({mins} мин). Сообщения за это время бот подтянет сам после подключения."),
        None))


async def check(ctx, mono: float | None = None) -> None:
    mono = time.monotonic() if mono is None else mono
    for name, (uz, ru) in PARTS.items():
        idle = mono - HEART.get(name, _STARTED)
        if idle >= STALL and name not in _down:
            _down.add(name)
            mins = int(idle // 60)
            await ctx.notifier.notify_owner(lambda uz=uz, ru=ru, mins=mins: (tr(
                f"🫀 «{uz}» {mins} daqiqadan beri ishlamayapti (qotib qolgan). Bot o'zi tiklashga urinadi; 10 daqiqada "
                "o'tmasa — Railway'da botni qayta ishga tushiring (Deployments → ⋮ → Restart).",
                f"🫀 «{ru}» не работает уже {mins} мин (завис). Бот пытается восстановиться; если за 10 мин не "
                "пройдёт — перезапустите бота в Railway (Deployments → ⋮ → Restart)."), None), key=f"stall-{name}")
        elif idle < STALL and name in _down:
            _down.discard(name)
            await ctx.notifier.resolve(f"stall-{name}", text=tr(f"✅ «{uz}» qayta ishlayapti.",
                                                                 f"✅ «{ru}» снова работает."))


async def loop(ctx) -> None:
    while True:
        await asyncio.sleep(EVERY)
        try:
            ctx.db.set("alive_ts", str(int(time.time())))
            await check(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Tiriklik tekshiruvi")
