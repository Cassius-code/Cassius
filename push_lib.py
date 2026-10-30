"""📚 Push kutubxonasi (egasi bilan kelishilgan, 2026-10-30).

* Har Push — raqam (№). Nomni bot o'zi beradi: «№7 · 🎤 ovozli · 29.10 14:30». Mazmuni o'qilmaydi va tahlil
  qilinmaydi (bu egasining g'oyasi) — faqat AYNAN bir xil nusxani tanish uchun iz (fp) saqlanadi.
* Bitta raqamli Push bitta lidga HECH QACHON ikki marta ketmaydi. Boshqa raqam — o'sha lidga ham ketishi mumkin
  (3 soat oralig'i saqlanadi).
* Matnni tahrirlash — raqam o'zgarmaydi. «🆕 Yangi Push» — yangi raqam.
* Yangi (hali hech kimga ketmagan) Push'ga oldingisi bilan aynan bir xil matn/fayl qo'yilsa — o'sha eski raqam
  deb olinadi (unga qayta yuborilmaydi)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime

KIND_UZ = {"voice": "🎤 ovozli", "video_note": "⭕ dumaloq video", "video": "🎬 video", "photo": "🖼 rasm",
           "audio": "🎵 audio", "animation": "🎞 gif", "document": "📄 fayl", "text": "📝 matn"}
KIND_RU = {"voice": "🎤 голосовое", "video_note": "⭕ кружок", "video": "🎬 видео", "photo": "🖼 фото",
           "audio": "🎵 аудио", "animation": "🎞 gif", "document": "📄 файл", "text": "📝 текст"}


def media_of(row) -> dict | None:
    if row is None or not row["media"]:
        return None
    try:
        m = json.loads(row["media"])
    except ValueError:
        return None
    return m if isinstance(m, dict) and m.get("kind") else None


def file_sha(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(text: str, media: dict | None) -> str:
    """Aynan bir xil nusxa izi: matn (bo'shliqlarsiz farq) + fayl (mazmunining sha256 yoki Telegram'ning
    o'zgarmas fayl ID si). Bo'sh Push — iz yo'q."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    m = ""
    if media:
        m = f"{media.get('kind')}:{media.get('sha') or media.get('uid') or media.get('file_id') or ''}"
    if not t and not m:
        return ""
    return hashlib.sha256(f"{t}\x00{m}".encode()).hexdigest()


def get(db, pid: int | None):
    return db.one("SELECT * FROM pushes WHERE id=?", (pid,)) if pid else None


def current(db):
    """Hozirgi (yuboriladigan) Push."""
    try:
        pid = int(db.get("push_current") or 0)
    except ValueError:
        pid = 0
    return get(db, pid)


def set_current(db, pid: int) -> None:
    db.set("push_current", str(pid))


def kind_of(text: str, media: dict | None) -> str:
    return media["kind"] if media else "text"


def create(db, text: str = "", media: dict | None = None, note: str = "", ts: int | None = None) -> int:
    now = int(ts or time.time())
    return int(db.run("INSERT INTO pushes(kind, text, media, fp, note, created_ts, updated_ts) VALUES(?,?,?,?,?,?,?)",
                      (kind_of(text, media), text or "", json.dumps(media) if media else "", fingerprint(text, media),
                       note[:60], now, now)).lastrowid)


def got_count(db, pid: int) -> int:
    """Shu raqamli Push'ni olgan lidlar (nazorat guruhisiz)."""
    return db.scalar("SELECT COUNT(*) FROM push_got WHERE push_id=? AND held=0", (pid,))


def sent_ever(db, pid: int) -> bool:
    return db.one("SELECT 1 FROM push_got WHERE push_id=? LIMIT 1", (pid,)) is not None or \
        db.one("SELECT 1 FROM broadcasts WHERE push_id=? AND sent>0 LIMIT 1", (pid,)) is not None


def same_as(db, fp: str, exclude: int):
    if not fp:
        return None
    return db.one("SELECT * FROM pushes WHERE fp=? AND id<>? ORDER BY id LIMIT 1", (fp, exclude))


def update(db, pid: int, text: str | None = None, media: dict | None | bool = False) -> tuple[int, int | None]:
    """Matn yoki media o'zgardi. Raqam o'zgarmaydi. Lekin hali hech kimga ketmagan Push oldingisi bilan aynan bir xil
    bo'lib qolsa — o'sha eski raqam bo'ladi (yangisi o'chadi). -> (hozirgi raqam, birlashgan eski raqam yoki None).
    media=False — o'zgarmaydi, None — olib tashlanadi."""
    row = get(db, pid)
    if row is None:
        return pid, None
    new_text = row["text"] if text is None else text
    new_media = media_of(row) if media is False else media
    fp = fingerprint(new_text, new_media)
    if not sent_ever(db, pid):
        old = same_as(db, fp, pid)
        if old is not None:
            db.run("DELETE FROM pushes WHERE id=?", (pid,))
            db.run("UPDATE pushes SET archived=0 WHERE id=?", (old["id"],))
            if str(db.get("push_current")) == str(pid):
                set_current(db, old["id"])
            return old["id"], old["id"]
    db.run("UPDATE pushes SET text=?, media=?, kind=?, fp=?, updated_ts=? WHERE id=?",
           (new_text, json.dumps(new_media) if new_media else "", kind_of(new_text, new_media), fp, int(time.time()),
            pid))
    return pid, None


def label(row, lang: str = "uz", tz=None) -> str:
    """«№7 · 🎤 ovozli · 29.10 14:30» — bot bergan nom (mazmun o'qilmaydi)."""
    if row is None:
        return "—"
    kinds = KIND_RU if lang == "ru" else KIND_UZ
    when = datetime.fromtimestamp(row["created_ts"], tz).strftime("%d.%m %H:%M") if row["created_ts"] else ""
    return " · ".join(x for x in (f"№{row['id']}", kinds.get(row["kind"], row["kind"]), when) if x)


def has_content(row) -> bool:
    return row is not None and bool((row["text"] or "").strip() or media_of(row))


def media_paths(db) -> set:
    out = set()
    for r in db.all("SELECT media FROM pushes WHERE media<>''"):
        m = media_of(r)
        if m and m.get("path"):
            out.add(m["path"])
    return out


def _old_media(raw: str | None) -> dict | None:
    """Eski yozuv: {"kind", "file_id", "path"} — fayl hali bor bo'lsa, mazmun izi (sha) ham qo'shiladi: keyin o'sha
    faylni qayta yuklasangiz, bot uni eski raqam deb taniydi."""
    try:
        m = json.loads(raw) if raw else None
    except ValueError:
        return None
    if not isinstance(m, dict) or not m.get("kind"):
        return None
    if m.get("path") and not m.get("sha"):
        sha = file_sha(m["path"])
        if sha:
            m["sha"] = sha
    return m


def migrate(db, now: int | None = None) -> None:
    """Bir marta: eski joriy matn/media — №1 (hozirgi), 📋 shablonlar — keyingi raqamlar. Bir xillari — bitta.
    Eski versiyada kimga qaysi matn ketgani yozilmagan — №1 hech kimga «olgan» deb yozilmaydi (egasi, 2026-10-30)."""
    if db.get("push_lib_v1"):
        return
    now = int(now or time.time())
    first = None
    text = db.get("push_text")
    m = _old_media(db.get("push_media"))
    if (text or "").strip() or m:
        first = create(db, text, m, ts=now)
        set_current(db, first)
    for t in db.all("SELECT * FROM templates ORDER BY id"):
        tm = _old_media(t["media"])
        if not (t["text"] or "").strip() and not tm:
            continue
        if same_as(db, fingerprint(t["text"], tm), 0) is None:
            create(db, t["text"], tm, note=t["name"], ts=now)
    db.set("push_lib_v1", "1")
