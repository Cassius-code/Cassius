"""Yagona SQLite baza (Railway Volume: /data/rdbot.sqlite3).

Mijoz va xodim xabarlarining MATNI saqlanmaydi: faqat kim, qachon, qaysi chat/topik, turi (video/matn).
Istisno: kassa cheklari va jarima/bonus xabarlari (ularni ega/xodim o'zi hisob uchun yozadi).
"""
from __future__ import annotations

import contextvars
import sqlite3
import threading
from pathlib import Path

from .config import DEFAULTS

# Panel tugmasi bosilganda: shu so'rov bazaga yozdimi (Orqaga — qayta ochish xavfsizmi, bilish uchun)
EFFECTS: contextvars.ContextVar = contextvars.ContextVar("db_effects", default=None)
_WRITE = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def mark_effect() -> None:
    c = EFFECTS.get()
    if c is not None:
        c[0] += 1


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- adminlar: owner (hammasi, egasining ulushi ham), full (boshqaruv), view (faqat ko'radi)
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    level TEXT NOT NULL DEFAULT 'full',
    name TEXT NOT NULL DEFAULT '',
    added_ts INTEGER NOT NULL DEFAULT 0
);

-- xodimlar (zaderjka nazorati va kassa uchun bitta ro'yxat)
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL DEFAULT '',        -- kichik harf, @ siz
    tg_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    kassa_kind TEXT NOT NULL DEFAULT '',      -- '' | worker | self | partner | pool
    zp_on INTEGER NOT NULL DEFAULT 1,         -- foiz bilan zp hisoblash
    attend INTEGER NOT NULL DEFAULT 1,        -- «доброе утро» / kech qolish nazorati
    days_off TEXT NOT NULL DEFAULT '',        -- dam olish kunlari: '0'..'6' (0 = dushanba)
    created_ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_people_tg ON people(tg_id);
CREATE INDEX IF NOT EXISTS idx_people_user ON people(username);

CREATE TABLE IF NOT EXISTS pct (
    person_id INTEGER NOT NULL,
    from_day TEXT NOT NULL,
    percent REAL NOT NULL,
    PRIMARY KEY (person_id, from_day)
);

CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    delay_on INTEGER NOT NULL DEFAULT 1,
    fine_usd REAL NOT NULL DEFAULT 0,         -- zaderjka jarimasi: bir martalik summa ($), 0 = jarimasiz
    push_on INTEGER NOT NULL DEFAULT 1,
    push_account_id INTEGER,
    push_limit INTEGER NOT NULL DEFAULT 0,
    quiet_from TEXT NOT NULL DEFAULT '',
    quiet_to TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS folder_people (
    folder_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    PRIMARY KEY (folder_id, person_id)
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    folder_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    is_forum INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'sync'
);

CREATE TABLE IF NOT EXISTS topics (
    chat_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '',
    created_ts INTEGER,
    PRIMARY KEY (chat_id, topic_id)
);

CREATE TABLE IF NOT EXISTS emoji_cache (doc_id INTEGER PRIMARY KEY, ch TEXT NOT NULL);

-- nit = forum topigi (topic_id>1) yoki oddiy chat (topic_id=0). Lid holati shu yerda.
CREATE TABLE IF NOT EXISTS threads (
    chat_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL DEFAULT 0,
    first_seen INTEGER,                       -- mijozning birinchi xabari
    last_seen INTEGER,                        -- mijozning oxirgi xabari
    last_activity INTEGER NOT NULL DEFAULT 0, -- har qanday oxirgi xabar
    msg_count INTEGER NOT NULL DEFAULT 0,
    seen_msg_id INTEGER NOT NULL DEFAULT 0,   -- ishlangan eng katta xabar id
    stavka TEXT NOT NULL DEFAULT '',          -- '' kuzatilmaydi | on | done
    stavka_from INTEGER,
    bets INTEGER NOT NULL DEFAULT 0,
    bet_last_ts INTEGER,
    bet_text_wait INTEGER NOT NULL DEFAULT 0, -- oxirgi videoning matni hali kelmagan
    stavka_end INTEGER,
    stavka_reminded INTEGER NOT NULL DEFAULT 0,  -- nechta «ставка» eslatmasi ketdi
    stavka_remind_ts INTEGER,                 -- oxirgi eslatma vaqti
    last_staff_ts INTEGER,                    -- xodimning oxirgi xabari (vositachi bot «aks-sadosi»ni ajratish uchun)
    wait_since INTEGER,                       -- zaderjka shu vaqtdan hisoblanadi (ketma-ket yozsa — oxirgisidan)
    wait_first INTEGER,                       -- javobsiz birinchi mijoz xabari (ketma-ket oynasi shundan)
    wait_msg_id INTEGER,
    alert_id INTEGER,
    last_push_ts INTEGER,
    cl_turn INTEGER,                          -- xodim yozdi, mijoz hali javob qaytarmadi: shu vaqtdan (soviyotgan lid)
    cl_avg INTEGER,                           -- mijoz odatda necha soniyada javob qaytaradi
    cl_n INTEGER NOT NULL DEFAULT 0,
    cool_noted INTEGER,                       -- shu «navbat» uchun «Проёб»da eslatildi (cl_turn qiymati) — qayta yo'q
    newlead_noted INTEGER,                    -- 🆕 yangi lid jimligi shu paytdan (oxirgi yozuv) eslatildi — qayta yo'q
    PRIMARY KEY (chat_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_threads_wait ON threads(wait_since);
CREATE INDEX IF NOT EXISTS idx_threads_stavka ON threads(stavka);
CREATE INDEX IF NOT EXISTS idx_threads_first ON threads(first_seen);

CREATE TABLE IF NOT EXISTS bets (
    chat_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, msg_id INTEGER NOT NULL, ts INTEGER NOT NULL,
    PRIMARY KEY (chat_id, topic_id, msg_id)
);

CREATE TABLE IF NOT EXISTS known_bots (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS known_humans (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '');

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL,
    wait_since INTEGER NOT NULL,
    wait_msg_id INTEGER,
    created_ts INTEGER NOT NULL,
    group_chat_id INTEGER,
    group_msg_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',      -- open | answered | done | void
    closed_ts INTEGER,
    closed_by TEXT,
    waited_min INTEGER,
    fine_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_ts);

-- «holat»: papkada bir vaqtda N+ lid javobsiz. Kuniga birinchi K tasi kechiriladi, keyin — ogohlantirishdan
-- so'ng G daqiqada javob bo'lmasa bir martalik jarima (papkaning har xodimiga)
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    seq INTEGER NOT NULL,                     -- shu kundagi nechanchi holat
    started_ts INTEGER NOT NULL,
    n_leads INTEGER NOT NULL,
    status TEXT NOT NULL,                     -- warn (kechirildi) | grace (kutilmoqda) | fined | ok
    deadline INTEGER,
    fine_usd REAL NOT NULL DEFAULT 0,
    group_chat_id INTEGER,
    group_msg_id INTEGER,
    ended_ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_incidents_folder ON incidents(folder_id, day);
CREATE TABLE IF NOT EXISTS incident_alerts (
    incident_id INTEGER NOT NULL, alert_id INTEGER NOT NULL, PRIMARY KEY (incident_id, alert_id)
);

CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, folder_id INTEGER NOT NULL,
    staff_id INTEGER, wait_since INTEGER NOT NULL, reply_ts INTEGER NOT NULL, work_seconds INTEGER NOT NULL,
    person_id INTEGER                         -- javob bergan xodim (papka akkauntidan bo'lsa — papkadagi yagona xodim)
);
CREATE INDEX IF NOT EXISTS idx_replies_ts ON replies(reply_ts);
CREATE INDEX IF NOT EXISTS idx_replies_thread ON replies(chat_id, topic_id);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at INTEGER NOT NULL, ts INTEGER NOT NULL, chat_id INTEGER NOT NULL, topic_id INTEGER NOT NULL DEFAULT 0,
    msg_id INTEGER, sender_id INTEGER, who TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_thread ON journal(chat_id, topic_id, id);
CREATE INDEX IF NOT EXISTS idx_journal_at ON journal(at);
CREATE INDEX IF NOT EXISTS idx_journal_ts ON journal(ts);

-- ishga kelish («доброе утро»)
CREATE TABLE IF NOT EXISTS attendance (
    day TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    arrived_ts INTEGER,
    late_min INTEGER NOT NULL DEFAULT 0,
    reminded INTEGER NOT NULL DEFAULT 0,
    greet_ts INTEGER,                         -- «доброе утро» yozilgan vaqt (kelgan vaqt — ishni boshlagani ham bo'lishi mumkin)
    last_act_ts INTEGER,                      -- 🔒 oxirgi marta lidga yozgan vaqt (joyida yo'qligini bilish uchun)
    PRIMARY KEY (day, person_id)
);
-- 🔒 qattiq rejim hodisalari: sekin javob (haftalik hisob) va joyida yo'q (boshlandi/tugadi)
CREATE TABLE IF NOT EXISTS strict_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER NOT NULL, kind TEXT NOT NULL, week TEXT, day TEXT,
    ts INTEGER NOT NULL, level INTEGER NOT NULL DEFAULT 1, adj_id INTEGER, folder_id INTEGER, act_ts INTEGER,
    ended_ts INTEGER, gid INTEGER, mid INTEGER
);
CREATE INDEX IF NOT EXISTS idx_strict_person ON strict_events(person_id, kind, week);

CREATE TABLE IF NOT EXISTS breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER,
    reminded INTEGER NOT NULL DEFAULT 0,
    minutes INTEGER                           -- «отойду на 15 минут» — aytilgan vaqt (umumiy limitdan oshmaydi)
);
CREATE TABLE IF NOT EXISTS pauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, folder_id INTEGER NOT NULL, start_ts INTEGER NOT NULL, end_ts INTEGER
);

-- ── kassa
CREATE TABLE IF NOT EXISTS prices (id INTEGER PRIMARY KEY AUTOINCREMENT, lo INTEGER NOT NULL, hi INTEGER NOT NULL,
                                   usd REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER, chat_id INTEGER, msg_id INTEGER, sender_id INTEGER,
    sender_name TEXT NOT NULL DEFAULT '', raw TEXT, status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL DEFAULT '',
    tag TEXT NOT NULL DEFAULT '',             -- hisobot tepasidagi notanish ism (yangi xodim sifatida taklif qilinadi)
    date_ok INTEGER NOT NULL DEFAULT 0        -- ⚠️ sana xato emasmi — so'raldi va javob berildi
);
CREATE INDEX IF NOT EXISTS idx_reports_person ON reports(person_id, status);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER NOT NULL, rd TEXT, amount INTEGER NOT NULL,
    usd REAL, skip INTEGER NOT NULL DEFAULT 0, pay INTEGER
);
CREATE INDEX IF NOT EXISTS idx_checks_report ON checks(report_id);
CREATE INDEX IF NOT EXISTS idx_checks_rd ON checks(rd);
-- jarima / bonus / avans ($)
CREATE TABLE IF NOT EXISTS adj (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER,
    kind TEXT,                                -- fine | bonus | adv
    usd REAL NOT NULL,
    day TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',    -- manual | group | delay | late | import
    note TEXT NOT NULL DEFAULT '',
    chat_id INTEGER, msg_id INTEGER, ref_id INTEGER,
    cancelled INTEGER NOT NULL DEFAULT 0,
    pending INTEGER NOT NULL DEFAULT 0,
    created_ts INTEGER NOT NULL DEFAULT 0,
    pct REAL                                  -- 🔒 qattiq rejim: kunlik zp ning % i (usd hisobotdan keyin hisoblanadi)
);
CREATE INDEX IF NOT EXISTS idx_adj_person ON adj(person_id, day);
-- 💸 jarima zinapoyasi: «zaderjka» (har kuni noldan) va «kech qolish» (har dushanba noldan): 1-si, 2-si …;
-- summa — egasi yozgani. period: zaderjka — kun, kech qolish — haftaning dushanbasi
CREATE TABLE IF NOT EXISTS strikes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER NOT NULL, kind TEXT NOT NULL, period TEXT NOT NULL,
    day TEXT NOT NULL, ts INTEGER NOT NULL, n INTEGER NOT NULL, usd REAL NOT NULL DEFAULT 0, folder_id INTEGER,
    ref TEXT NOT NULL DEFAULT '', adj_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_strikes_person ON strikes(person_id, kind, period);
CREATE INDEX IF NOT EXISTS idx_strikes_ts ON strikes(ts);
-- 📅 bugun kim qayerda: shu kunga RD xodimi (odatdagisi o'rniga) va «bugun ishlamaydi»
CREATE TABLE IF NOT EXISTS roster (
    day TEXT NOT NULL, folder_id INTEGER NOT NULL, person_id INTEGER NOT NULL, ts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, folder_id)
);
CREATE TABLE IF NOT EXISTS roster_off (
    day TEXT NOT NULL, person_id INTEGER NOT NULL, ts INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, person_id)
);
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, from_id INTEGER NOT NULL, to_id INTEGER NOT NULL,
    pct REAL NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0
);
-- ulush: to_id oladi, from_id kassasidan (base=kassa) yoki zp sidan (base=zp);
-- mode: owner — siz to'laysiz, partner — Artur to'laydi, deduct — from_id zp sidan ushlanadi
CREATE TABLE IF NOT EXISTS shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT, to_id INTEGER NOT NULL, from_id INTEGER NOT NULL, pct REAL NOT NULL,
    base TEXT NOT NULL DEFAULT 'zp', mode TEXT NOT NULL DEFAULT 'deduct', from_day TEXT NOT NULL DEFAULT '2000-01-01',
    to_day TEXT NOT NULL DEFAULT '9999-12-31', active INTEGER NOT NULL DEFAULT 1
);
-- haftalik foizlar: sizning foizingiz akkaunt kassasidan (qolgani Arturga)
CREATE TABLE IF NOT EXISTS owner_pct (
    acct INTEGER NOT NULL, from_day TEXT NOT NULL, pct REAL NOT NULL, PRIMARY KEY (acct, from_day)
);
-- «🧮 Haftani hisoblash»: tasdiqlangan haftalar (dushanba)
CREATE TABLE IF NOT EXISTS weeks (week TEXT PRIMARY KEY, ts INTEGER NOT NULL, actor INTEGER);
-- «💸 Oylik berildi»: shu kungacha (upto_day) hisob yopildi
CREATE TABLE IF NOT EXISTS payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER NOT NULL, upto_day TEXT NOT NULL, ts INTEGER NOT NULL,
    total REAL, note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_payouts_person ON payouts(person_id, upto_day);
-- kassa tarixi: kim, qachon, nimani o'zgartirdi (eski → yangi). Matn emas, faqat raqamlar.
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, actor INTEGER, kind TEXT NOT NULL,
    person_id INTEGER, day TEXT, ref_id INTEGER, old TEXT NOT NULL DEFAULT '', new TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_day ON audit(day);
CREATE INDEX IF NOT EXISTS idx_audit_person ON audit(person_id, day);
-- boshlang'ich kassa (cheklar yig'indisi, oldingi haftalar): umumiy reytingda yangi cheklar ustiga qo'shiladi.
-- Nom bo'yicha (xodimlar qayta kiritilsa ham saqlanadi)
CREATE TABLE IF NOT EXISTS opening (name TEXT PRIMARY KEY COLLATE NOCASE, raw INTEGER NOT NULL);
-- «✅ Kunni yopish»: yopilgan kunni faqat ega o'zgartira oladi
CREATE TABLE IF NOT EXISTS closed_days (
    day TEXT PRIMARY KEY, ts INTEGER NOT NULL, actor INTEGER, n INTEGER NOT NULL DEFAULT 0,
    raw INTEGER NOT NULL DEFAULT 0, usd REAL NOT NULL DEFAULT 0
);
-- kirish so'rovlari va xodim «oyligim» so'rovlari
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, tg_id INTEGER NOT NULL, name TEXT NOT NULL DEFAULT '',
    arg TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open'
);

-- ── Push
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, session TEXT NOT NULL DEFAULT '', user_id INTEGER,
    label TEXT NOT NULL DEFAULT '', paused INTEGER NOT NULL DEFAULT 0, added_ts INTEGER NOT NULL DEFAULT 0,
    spam TEXT NOT NULL DEFAULT '', spam_ts INTEGER        -- @SpamBot: '' noma'lum · ok · limited
);
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', media TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_ts INTEGER NOT NULL, finished_ts INTEGER, trigger TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running', kind TEXT NOT NULL DEFAULT '',
    slot TEXT NOT NULL DEFAULT '',            -- 🌅 morning / ☀️ day: uzilsa — davom etish shu tartibda
    push_id INTEGER,                          -- 📚 qaysi Push (raqami)
    control INTEGER NOT NULL DEFAULT 0        -- 🧪 10% nazorat guruhi bilan yuborilgan
);
-- har Push'ni kim oldi: keyin yozdimi (90 daqiqa) va kartagacha yetdimi (24 soat) — oxirgi Push'ga yoziladi.
-- held=1 — 🧪 nazorat guruhi: Push yuborilmadi (taqqoslash uchun — ular ham o'zi yozdimi)
CREATE TABLE IF NOT EXISTS push_log (
    bid INTEGER NOT NULL, chat_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, folder_id INTEGER,
    ts INTEGER NOT NULL, replied_ts INTEGER, card_ts INTEGER, held INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bid, chat_id, topic_id)
);
-- 📚 Push kutubxonasi: har Push — raqam. Nomni bot beradi (№ · turi · sana); mazmun o'qilmaydi, faqat aynan bir
-- xil nusxani tanish uchun iz (fp) saqlanadi
CREATE TABLE IF NOT EXISTS pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'text', text TEXT NOT NULL DEFAULT '',
    media TEXT NOT NULL DEFAULT '', fp TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    created_ts INTEGER NOT NULL DEFAULT 0, updated_ts INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pushes_fp ON pushes(fp);
-- bitta raqamli Push bitta lidga hech qachon ikki marta ketmaydi (held=1 — nazorat guruhi, olmagan)
CREATE TABLE IF NOT EXISTS push_got (
    push_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, ts INTEGER NOT NULL,
    bid INTEGER, held INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (push_id, chat_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_push_log_thread ON push_log(chat_id, topic_id, ts);
-- ⏰ javobsiz zaderjka: eslatma (zaderjka xabariga javob) va muhlatdan keyin jarima — har zaderjka xabariga bitta
CREATE TABLE IF NOT EXISTS alert_reminders (
    gid INTEGER NOT NULL, mid INTEGER NOT NULL, folder_id INTEGER, reminded_ts INTEGER NOT NULL, rgid INTEGER,
    rmid INTEGER, deadline INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open', ended_ts INTEGER,
    PRIMARY KEY (gid, mid)
);
-- 🧹 «Проёб»dagi bot xabarlari: vaqti kelganda o'chadi (delay — yopilgan vaqtdan, info — yozilgan vaqtdan)
CREATE TABLE IF NOT EXISTS group_msgs (
    gid INTEGER NOT NULL, mid INTEGER NOT NULL, kind TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY (gid, mid)
);
-- Push: yuborib bo'lmagan lidlar (Push yangilanish sababli uzilib, keyin davom etsa — ularga qayta urinilmaydi)
CREATE TABLE IF NOT EXISTS push_fail (
    bid INTEGER NOT NULL, chat_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, folder_id INTEGER, ts INTEGER
);
CREATE INDEX IF NOT EXISTS idx_push_fail_bid ON push_fail(bid);
-- lidga karta yuborildi (xodim /rek /dep /cash yozdi): kim, qachon, qaysi lid. Matn saqlanmaydi — faqat buyruq so'zi
CREATE TABLE IF NOT EXISTS cards (
    chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL, topic_id INTEGER NOT NULL, folder_id INTEGER,
    sender_id INTEGER, person_id INTEGER, cmd TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL,
    reminded INTEGER NOT NULL DEFAULT 0,      -- 💳 to'lov eslatmasi ketdi (karta ketgach hech kim yozmagan)
    PRIMARY KEY (chat_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_cards_thread ON cards(chat_id, topic_id, ts);
CREATE INDEX IF NOT EXISTS idx_cards_ts ON cards(ts);
-- bir nechta odamga borgan savol/ogohlantirish nusxalari: biri hal qilsa — hammasi o'chadi/yangilanadi
CREATE TABLE IF NOT EXISTS sent (
    key TEXT NOT NULL, chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL, ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sent_key ON sent(key);
CREATE TABLE IF NOT EXISTS ignored_msgs (
    chat_id INTEGER NOT NULL, msg_id INTEGER NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY (chat_id, msg_id)
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        for _ in range(30):                         # eski baza: indeks yangi ustunga tayansa — avval ustun qo'shiladi
            try:
                self.conn.executescript(SCHEMA)
                break
            except sqlite3.OperationalError as exc:
                if "no such column" not in str(exc):
                    raise
                self._add_missing_columns()
        else:
            raise RuntimeError("baza sxemasini yangilab bo'lmadi")
        self._add_missing_columns()
        self._cache: dict[str, str] = {}

    def _add_missing_columns(self) -> None:
        """Oldingi versiya bazasi: yangi ustunlar qo'shiladi (ma'lumot o'chmaydi)."""
        ref = sqlite3.connect(":memory:")
        try:
            ref.executescript(SCHEMA)
            tables = [r[0] for r in ref.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                "AND name NOT LIKE 'sqlite_%'")]
            for t in tables:
                have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({t})")}
                if not have:                        # jadval hali yo'q — SCHEMA o'zi yaratadi
                    continue
                for _cid, name, typ, notnull, dflt, _pk in ref.execute(f"PRAGMA table_info({t})"):
                    if name in have:
                        continue
                    col = f"{name} {typ}"
                    if dflt is not None:
                        col += f" {'NOT NULL ' if notnull else ''}DEFAULT {dflt}"
                    self.conn.execute(f"ALTER TABLE {t} ADD COLUMN {col}")
        finally:
            ref.close()

    # ------------------------------------------------------------ umumiy
    def run(self, sql: str, params=()) -> sqlite3.Cursor:
        if sql.lstrip()[:7].upper().startswith(_WRITE):
            mark_effect()
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def many(self, sql: str, rows) -> None:
        mark_effect()
        with self._lock:
            self.conn.executemany(sql, rows)

    def one(self, sql: str, params=()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def all(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def scalar(self, sql: str, params=(), default=0):
        row = self.one(sql, params)
        return default if row is None or row[0] is None else row[0]

    def tx(self):
        """with db.tx(): … — bir nechta o'zgarishni bitta tranzaksiyada."""
        db = self

        class _Tx:
            def __enter__(self):
                mark_effect()
                db._lock.acquire()
                db.conn.execute("BEGIN")
                return db

            def __exit__(self, et, ev, tb):
                try:
                    db.conn.execute("ROLLBACK" if et else "COMMIT")
                finally:
                    db._lock.release()
                return False
        return _Tx()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    # ------------------------------------------------------------ sozlamalar (kesh bilan: panel tez ishlaydi)
    def get(self, key: str) -> str:
        if key in self._cache:
            return self._cache[key]
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        value = row["value"] if row else DEFAULTS.get(key, "")
        self._cache[key] = value
        return value

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(float(self.get(key) or default))
        except ValueError:
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key) or default)
        except ValueError:
            return default

    def set(self, key: str, value) -> None:
        value = str(value)
        self.run("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
        self._cache[key] = value

    def flag(self, key: str) -> bool:
        return self.get(key) == "1"

    def toggle(self, key: str) -> bool:
        new = not self.flag(key)
        self.set(key, "1" if new else "0")
        return new
