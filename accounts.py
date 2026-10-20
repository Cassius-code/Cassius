"""Push akkauntlari (har papkaga o'zi): faqat yuboradi, hech narsa o'qimaydi."""
from __future__ import annotations

import asyncio
import logging

from .tgclient import TgAccount
from .tgsend import PushSender

log = logging.getLogger("accounts")

MAIN = -1          # papka Push'i asosiy akkauntdan (alohida sessiya ochilmaydi — o'sha ulanish ishlatiladi)


class PushAccount(TgAccount, PushSender):
    def __init__(self, cfg, db, notifier, acc_id: int, on_identified=None):
        super().__init__(cfg, db, notifier)
        self.acc_id = acc_id
        self.on_identified = on_identified

    def row(self):
        return self.db.one("SELECT * FROM accounts WHERE id=?", (self.acc_id,))

    def session(self) -> str:
        r = self.row()
        return r["session"] if r else ""

    def title(self) -> str:
        r = self.row()
        return f"Push «{r['name']}»" if r else f"Push #{self.acc_id}"

    async def on_online(self, client) -> None:
        self.db.run("UPDATE accounts SET user_id=?, label=? WHERE id=?", (self.me_id, self.me_label, self.acc_id))
        if self.on_identified:
            try:
                self.on_identified()
            except Exception:
                log.warning("Push akkaunt ID si yangilanmadi")
        try:
            await client.get_dialogs(limit=None)          # chatlar keshi: Push ValueError bermasin
            self._dialogs_refreshed = True
        except Exception:
            pass


class AccountPool:
    def __init__(self, cfg, db, notifier, on_identified=None):
        self.cfg, self.db, self.notifier = cfg, db, notifier
        self.on_identified = on_identified
        self.accounts: dict[int, PushAccount] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self.main = None                      # asosiy akkaunt (Userbot) — Push uchun ham tanlash mumkin

    async def _runner(self, acc: PushAccount) -> None:
        while True:
            try:
                await acc.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Push akkaunt %s yiqildi", acc.acc_id)
            await asyncio.sleep(10)

    def sync(self) -> None:
        wanted = {r["id"] for r in self.db.all("SELECT id FROM accounts WHERE paused=0 AND session<>''")}
        for acc_id in wanted - set(self.accounts):
            acc = PushAccount(self.cfg, self.db, self.notifier, acc_id, self.on_identified)
            self.accounts[acc_id] = acc
            self._tasks[acc_id] = asyncio.create_task(self._runner(acc))
        for acc_id in set(self.accounts) - wanted:
            self._tasks.pop(acc_id).cancel()
            acc = self.accounts.pop(acc_id)
            asyncio.create_task(acc._disconnect())

    def sender(self, acc_id: int | None):
        if acc_id == MAIN:
            return self.main
        return self.accounts.get(acc_id) if acc_id else None

    def state_of(self, acc_id: int | None) -> str:
        if acc_id == MAIN:
            return self.main.state if self.main is not None else "no_session"
        row = self.db.one("SELECT paused FROM accounts WHERE id=?", (acc_id,)) if acc_id else None
        if row is not None and row["paused"]:
            return "paused"
        acc = self.sender(acc_id)
        return acc.state if acc is not None else "no_session"

    async def stop(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        for acc in self.accounts.values():
            await acc._disconnect()
