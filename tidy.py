"""🧹 «Проёб» toza tursin: botning o'z xabarlari vaqti kelganda o'zi o'chadi (sozlamani egasi boshqaradi).

* «задержка» xabari — xodim javob berib, xabardagi hamma lid yopilgandan N daqiqa keyin (clean_delay_min, 10);
* boshqa avtomat xabarlar («остывают», «Опоздание», «Пуш завершён», jarima, «ставка», kun oxiri, tanaffus,
  «доброе утро» eslatmasi) — yozilganidan N daqiqa keyin (clean_info_min, 60).
0 — o'chirmaydi. Buyruq bilan chaqirilganlar (/topweek, /statistika …), haftalik xulosa va 📌 doska o'chmaydi.
Hisob-kitob (kim javob berdi, jarima, statistika) botning bazasida qoladi — faqat chatdagi xabar o'chadi."""
from __future__ import annotations

import logging

log = logging.getLogger("tidy")

MAX_AGE = 47 * 3600          # Telegram 48 soatdan eski xabarni o'chirtirmaydi
DELAY_CHOICES = (0, 5, 10, 15, 30, 60)
INFO_CHOICES = (0, 30, 60, 120, 180)


def remember(db, gid: int, mid: int, kind: str, ts: int) -> None:
    """kind: delay (ts — yopilgan vaqt) | info (ts — yozilgan vaqt)."""
    db.run("INSERT OR IGNORE INTO group_msgs(gid, mid, kind, ts) VALUES(?,?,?,?)", (int(gid), int(mid), kind, int(ts)))


def minutes(db, kind: str) -> int:
    return max(0, db.get_int("clean_delay_min" if kind == "delay" else "clean_info_min", 10 if kind == "delay" else 60))


async def sweep(ctx, now: int) -> int:
    """Vaqti kelganlarini o'chiradi. Sozlama o'zgarsa — navbatdagilarga ham darhol ta'sir qiladi. -> nechta."""
    db = ctx.db
    lim = {"delay": minutes(db, "delay"), "info": minutes(db, "info")}
    n = 0
    for row in db.all("SELECT gid, mid, kind, ts FROM group_msgs ORDER BY ts LIMIT 300"):
        if now - row["ts"] > MAX_AGE:
            db.run("DELETE FROM group_msgs WHERE gid=? AND mid=?", (row["gid"], row["mid"]))
            continue
        m = lim.get(row["kind"], 0)
        if m <= 0 or now < row["ts"] + m * 60:
            continue
        try:
            await ctx.notifier.delete_group(row["gid"], row["mid"])
            n += 1
        except Exception as exc:
            log.info("Xabar o'chmadi %s/%s: %s", row["gid"], row["mid"], exc)
        db.run("DELETE FROM group_msgs WHERE gid=? AND mid=?", (row["gid"], row["mid"]))
    return n
