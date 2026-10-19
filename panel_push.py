"""📣 Push: matn/media, papkalar (akkaunt, soni, tinch vaqt), jadval (avtomat), sozlamalar, yuborish, jurnal."""
from __future__ import annotations

import json
import os
import re
import uuid

from . import people as P
from . import ui
from .push import push_times
from .timeutil import fmt, parse_date, parse_hhmm, parse_minutes, parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title, must

MAX_MEDIA = 20 * 1024 * 1024
SPEED_UZ = {"fast": "tez 1–2 s", "normal": "oddiy 2–3 s", "slow": "ehtiyot 3–5 s"}
SPEED_RU = {"fast": "быстро 1–2 с", "normal": "обычно 2–3 с", "slow": "осторожно 3–5 с"}
KIND_UZ = {"voice": "🎤 ovozli", "video_note": "⭕ dumaloq video", "video": "🎬 video", "photo": "🖼 rasm",
           "audio": "🎵 audio", "animation": "🎞 gif", "document": "📄 fayl"}
KIND_RU = {"voice": "🎤 голосовое", "video_note": "⭕ кружок", "video": "🎬 видео", "photo": "🖼 фото",
           "audio": "🎵 аудио", "animation": "🎞 gif", "document": "📄 файл"}


def acc_name(ctx, acc_id) -> str:
    a = ctx.db.one("SELECT name FROM accounts WHERE id=?", (acc_id,)) if acc_id else None
    return a["name"] if a else "—"


def state_icon(ctx, acc_id) -> str:
    st = ctx.pool.state_of(acc_id) if ctx.pool else "no_session"
    return {"online": "🟢", "connecting": "🟡", "starting": "🟡", "paused": "⏸"}.get(st, "🔴")


@screen("u", "full")
async def push_menu(ctx, r: Req):
    db, pu = ctx.db, ctx.pusher
    text = db.get("push_text").strip()
    media = pu.media()
    preview = h(text[:140]) + ("…" if len(text) > 140 else "") if text else r.L("<i>matn yo'q</i>", "<i>нет текста</i>")
    kinds = KIND_RU if r.lang == "ru" else KIND_UZ
    plan = []
    for f in P.folders(db):
        if not f["push_on"]:
            continue
        n = f["push_limit"] or db.get_int("push_limit")
        plan.append(f"📁 {h(f['name'])} → {state_icon(ctx, f['push_account_id'])} {h(acc_name(ctx, f['push_account_id']))}"
                    f" · <b>{n or r.L('hammasi', 'все')}</b>")
    auto = (r.L("🟢 avtomat: ", "🟢 авто: ") + ", ".join(push_times(db))) if db.flag("push_auto") else \
        r.L("⚪ avtomat o'ch", "⚪ авто выкл")
    parts = [title("📣", "PUSH", r.L("issiq lidlarga xabar", "сообщение горячим лидам")), "",
             card([f"<b>{r.L('Matn', 'Текст')}</b>", preview] +
                  ([f"📎 {kinds.get(media['kind'], media['kind'])}"] if media else [])),
             card([f"<b>{r.L('Reja', 'План')}</b>"] + (plan or [r.L("Push yoqilgan papka yo'q", "Нет папок с Push")]) +
                  [f"⏰ {auto}"])]
    if pu.running:
        parts.append(card([f"⏳ {r.L('Yuborilmoqda', 'Идёт рассылка')}… {h(pu.progress_text)}"]))
    rows = []
    if pu.running:
        rows.append([(r.L("⏹ To'xtatish", "⏹ Остановить"), "ux")])
    else:
        rows += grid([(r.L("🚀 Yuborish", "🚀 Разослать"), "us"), (r.L("🧪 Test (o'zimga)", "🧪 Тест (себе)"), "ut")])
    rows += grid([(r.L("✏️ Matn", "✏️ Текст"), "ue"), (r.L("📎 Media", "📎 Медиа"), "um"),
                  (r.L("📋 Shablonlar", "📋 Шаблоны"), "ul"), (r.L("📁 Papkalar", "📁 Папки"), "uf"),
                  (r.L("⏰ Jadval", "⏰ Расписание"), "uj"), (r.L("⚙️ Sozlamalar", "⚙️ Настройки"), "uo"),
                  (r.L("🧾 Jurnal", "🧾 Журнал"), "uh")])
    rows.append(nav(r))
    return ui.join(*parts), kb(*rows)


# ───────────────────────── yuborish
@screen("us", "full")
async def start_preview(ctx, r: Req):
    pu = ctx.pusher
    if not pu.has_content():
        return r.L("⚠️ Avval matn yoki media qo'shing", "⚠️ Сначала добавьте текст или медиа")
    aud = pu.audience("all")
    n = len(aud["items"])
    folders = {f["id"]: f for f in P.folders(ctx.db)}
    lines = [f"📁 {h(folders[fid]['name'])} → <b>{q}</b>" for fid, q in aud["by_folder"].items() if q]
    skipped = [(r.L("yangi (stavka)", "новые (ставка)"), aud["fresh"]), (r.L("yaqinda yozishgan", "недавно писали"),
                                                                        aud["cooled"]),
               (r.L("yaqinda Push olgan", "уже получали"), aud["repeated"])]
    sk = ", ".join(f"{a} {b}" for a, b in skipped if b)
    info = [r.L(f"Qabul qiluvchilar: <b>{n}</b>", f"Получателей: <b>{n}</b>"),
            r.L(f"Vaqt: ≈ <b>{pu.estimate_minutes(n)} daq</b>", f"Время: ≈ <b>{pu.estimate_minutes(n)} мин</b>")]
    if sk:
        info.append(r.L("O'tkazildi: ", "Пропущено: ") + sk)
    if aud["no_account"]:
        info.append("⚠️ " + r.L("Akkauntsiz papkalar: ", "Папки без аккаунта: ") +
                    h(", ".join(folders[f]["name"] for f in aud["no_account"])))
    if aud["quiet"]:
        info.append("🌙 " + r.L("Tinch vaqtda: ", "Тихое время: ") + h(", ".join(folders[f]["name"] for f in aud["quiet"])))
    text = ui.join(title("🚀", r.L("PUSHNI TASDIQLANG", "ПОДТВЕРДИТЕ PUSH")), "", card(info), card(lines) if lines else "")
    rows = [[(r.L("✅ Boshlash", "✅ Начать"), "usy")]] if n else []
    rows.append(nav(r, "u"))
    return text, kb(*rows)


@screen("usy", "full")
async def start_run(ctx, r: Req):
    pu = ctx.pusher
    if pu.running:
        return r.L("⏳ Push allaqachon ketyapti", "⏳ Рассылка уже идёт")
    chat_id, mid = r.chat_id, r.message.message_id

    async def progress(sent, failed, total):
        pu.progress_text = f"{sent}/{total}" + (f" · ✖️{failed}" if failed else "")
        try:
            await ui.show(ctx.bot, chat_id, ui.join(title("📣", "PUSH"), "", card(
                [f"⏳ {r.L('Yuborilmoqda', 'Идёт рассылка')}: <b>{sent}/{total}</b>" +
                 (f" · ✖️ {failed}" if failed else "")])), kb([(r.L("⏹ To'xtatish", "⏹ Остановить"), "ux")]),
                edit_id=mid)
        except Exception:
            pass

    async def job():
        res = await pu.run("manual", "all", progress)
        pu.progress_text = ""
        await ui.show(ctx.bot, chat_id, report_text(ctx, r, res), kb([("📣 Push", "u"), (r.L("⌂ Menyu", "⌂ Меню"), "m")]),
                      edit_id=mid)

    ui.bg(job())
    return ui.join(title("📣", "PUSH"), "", card([r.L("⏳ Boshlandi…", "⏳ Начинаю…")])), \
        kb([(r.L("⏹ To'xtatish", "⏹ Остановить"), "ux")])


def report_text(ctx, r: Req, res: dict) -> str:
    names = {"done": r.L("✅ Push tugadi", "✅ Рассылка завершена"), "stopped": r.L("⏹ To'xtatildi", "⏹ Остановлено"),
             "aborted": r.L("⛔ Push uzildi", "⛔ Рассылка прервана"), "busy": r.L("⏳ Boshqa Push ketyapti",
                                                                              "⏳ Другая рассылка идёт"),
             "empty": r.L("⚠️ Matn yo'q", "⚠️ Нет текста"), "disabled": r.L("⛔ Push o'chirilgan", "⛔ Push выключен"),
             "interrupted": r.L("⚠️ Qayta ishga tushish sababli uzildi", "⚠️ Прервано перезапуском")}
    lines = [f"<b>{names.get(res['status'], res['status'])}</b>"]
    if "sent" in res:
        lines.append(r.L(f"Yuborildi: <b>{res['sent']}</b> / {res['total']}", f"Отправлено: <b>{res['sent']}</b> / "
                                                                             f"{res['total']}")
                     + (f" · ✖️ {res['failed']}" if res["failed"] else ""))
        folders = {f["id"]: f for f in P.folders(ctx.db)}
        for fid, (ok, bad) in res.get("per_folder", {}).items():
            if fid in folders:
                lines.append(f"📁 {h(folders[fid]['name'])}: {ok}" + (f" · ✖️ {bad}" if bad else ""))
        if res.get("reasons"):
            top = sorted(res["reasons"].items(), key=lambda kv: -kv[1])[:3]
            lines.append(r.L("Sabablar: ", "Причины: ") + "; ".join(f"{h(k)} ×{v}" for k, v in top))
    return ui.join(title("📣", "PUSH"), "", card(lines))


@screen("ux", "full")
async def stop(ctx, r: Req):
    ctx.pusher.stop()
    await ui.toast(ctx.bot, r.chat_id, r.L("⏹ To'xtatildi", "⏹ Остановлено"))
    return await push_menu(ctx, r)


@screen("ut", "full")
async def test(ctx, r: Req):
    try:
        await ctx.pusher.send_test(ctx.bot, r.chat_id)
    except ValueError:
        return r.L("⚠️ Matn yoki media yo'q", "⚠️ Нет текста или медиа")
    except Exception as exc:
        return r.L(f"⚠️ Yuborilmadi: {h(exc)}", f"⚠️ Не отправлено: {h(exc)}")
    await ui.toast(ctx.bot, r.chat_id, r.L("🧪 Sinov xabari yuborildi ⬆️ (faqat sizga)", "🧪 Тест отправлен ⬆️ (только вам)"))
    return await push_menu(ctx, r)


# ───────────────────────── matn va media
@screen("ue", "full")
async def text_ask(ctx, r: Req):
    ui.ask(r, "push_text", "u")
    return title("✏️", r.L("PUSH MATNI", "ТЕКСТ PUSH")) + "\n\n" + card(
        [r.L("Matnni yuboring (3500 belgigacha). <code>-</code> — matnni olib tashlash.",
             "Пришлите текст (до 3500 символов). <code>-</code> — убрать текст.")]), ui.cancel_kb(r, "u")


@on_input("push_text")
async def text_set(ctx, r: Req):
    text = r.message.text if r.message is not None and r.message.text else r.text
    if text.strip() in ("-", "—"):
        ctx.db.set("push_text", "")
    else:
        if len(text) > 3500:
            return r.L("⚠️ 3500 belgidan oshmasin", "⚠️ Не больше 3500 символов")
        ctx.db.set("push_text", text)
    return await push_menu(ctx, r)


def extract_media(message):
    if message.voice:
        return "voice", message.voice.file_id, message.voice.file_size, ".ogg"
    if message.video_note:
        return "video_note", message.video_note.file_id, message.video_note.file_size, ".mp4"
    if message.video:
        return "video", message.video.file_id, message.video.file_size, ".mp4"
    if message.animation:
        return "animation", message.animation.file_id, message.animation.file_size, ".mp4"
    if message.photo:
        ph = message.photo[-1]
        return "photo", ph.file_id, ph.file_size, ".jpg"
    if message.audio:
        return "audio", message.audio.file_id, message.audio.file_size, ".mp3"
    if message.document:
        d = message.document
        return "document", d.file_id, d.file_size, (os.path.splitext(d.file_name or "")[1][:8] or ".bin")
    return None


@screen("um", "full")
async def media_ask(ctx, r: Req):
    ui.ask(r, "push_media", "u")
    rows = [[(r.L("🗑 Mediani olib tashlash", "🗑 Убрать медиа"), "umx")]] if ctx.pusher.media() else []
    rows.append([(r.L("✖️ Bekor qilish", "✖️ Отмена"), "u")])
    return title("📎", r.L("PUSH MEDIASI", "МЕДИА PUSH")) + "\n\n" + card(
        [r.L("Yuboring: 🎤 ovozli, ⭕ dumaloq video, 🎬 video, 🖼 rasm yoki fayl (20 MB gacha). Matn izoh bo'lib ketadi.",
             "Пришлите: 🎤 голосовое, ⭕ кружок, 🎬 видео, 🖼 фото или файл (до 20 МБ). Текст пойдёт подписью.")]), \
        kb(*rows)


@screen("umx", "full")
async def media_remove(ctx, r: Req):
    drop_media(ctx, ctx.pusher.media())
    ctx.db.set("push_media", "")
    return await push_menu(ctx, r)


def drop_media(ctx, media) -> None:
    if not media or not media.get("path"):
        return
    used = {json.loads(t["media"]).get("path") for t in ctx.db.all("SELECT media FROM templates WHERE media<>''")}
    if media["path"] not in used:
        try:
            os.remove(media["path"])
        except OSError:
            pass


@on_input("push_media")
async def media_set(ctx, r: Req):
    m = r.message
    found = extract_media(m) if m is not None else None
    if found is None:
        return r.L("⚠️ Media yuboring (ovozli, video, rasm…)", "⚠️ Пришлите медиа (голосовое, видео, фото…)")
    kind, file_id, size, ext = found
    if size and size > MAX_MEDIA:
        return r.L("⚠️ 20 MB dan katta", "⚠️ Больше 20 МБ")
    folder = os.path.join(str(ctx.cfg.data_dir), "push_media")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    try:
        await ctx.bot.download(file_id, destination=path)
    except Exception as exc:
        return r.L(f"⚠️ Yuklab bo'lmadi ({type(exc).__name__})", f"⚠️ Не удалось скачать ({type(exc).__name__})")
    old = ctx.pusher.media()
    ctx.db.set("push_media", json.dumps({"kind": kind, "file_id": file_id, "path": path}))
    drop_media(ctx, old)
    return await push_menu(ctx, r)


# ───────────────────────── shablonlar
@screen("ul", "full")
async def templates(ctx, r: Req):
    db = ctx.db
    a = r.args
    if a and a[0] == "u":
        t = db.one("SELECT * FROM templates WHERE id=?", (int(a[1]),))
        if t:
            db.set("push_text", t["text"])
            db.set("push_media", t["media"])
            await ui.toast(ctx.bot, r.chat_id, r.L("✅ Shablon qo'llandi", "✅ Шаблон применён"))
            return await push_menu(ctx, r)
    if a and a[0] == "d":
        db.run("DELETE FROM templates WHERE id=?", (int(a[1]),))
    rows = []
    for t in db.all("SELECT * FROM templates ORDER BY id"):
        rows.append([(f"▶️ {t['name']}" + (" 📎" if t["media"] else ""), f"ul:u:{t['id']}"), ("🗑", f"ul:d:{t['id']}")])
    rows.append([(r.L("💾 Joriyni saqlash", "💾 Сохранить текущий"), "ula")])
    rows.append(nav(r, "u"))
    return ui.join(title("📋", r.L("SHABLONLAR", "ШАБЛОНЫ")), "",
                   card([r.L("▶️ — qo'llash, 🗑 — o'chirish.", "▶️ — применить, 🗑 — удалить.")])), kb(*rows)


@screen("ula", "full")
async def template_save_ask(ctx, r: Req):
    if not ctx.pusher.has_content():
        return r.L("⚠️ Avval matn yoki media qo'shing", "⚠️ Сначала добавьте текст или медиа")
    ui.ask(r, "tpl_name", "ul")
    return title("💾", r.L("SHABLON NOMI", "НАЗВАНИЕ ШАБЛОНА")) + "\n\n" + card(
        [r.L("Nom yuboring, masalan <code>Ertalabki</code>.", "Пришлите название, например <code>Утро</code>.")]), \
        ui.cancel_kb(r, "ul")


@on_input("tpl_name")
async def template_save(ctx, r: Req):
    name = r.text.strip()[:40]
    if not name:
        return r.L("⚠️ Nom kerak", "⚠️ Нужно название")
    ctx.db.run("INSERT INTO templates(name, text, media) VALUES(?,?,?)", (name, ctx.db.get("push_text"),
                                                                         ctx.db.get("push_media")))
    r.args = []
    return await templates(ctx, r)


# ───────────────────────── papkalar (akkaunt, soni, tinch vaqt)
@screen("uf", "full")
async def folders(ctx, r: Req):
    db = ctx.db
    if r.args:
        return await folder_card(ctx, r)
    rows = []
    for f in P.folders(db):
        n = f["push_limit"] or db.get_int("push_limit")
        mark = "✅" if f["push_on"] else "▫️"
        rows.append([(f"{mark} {f['name']} · {state_icon(ctx, f['push_account_id'])} {acc_name(ctx, f['push_account_id'])}"
                      f" · {n or '∞'}"[:60], f"uf:{f['id']}")])
    rows.append(nav(r, "u"))
    return ui.join(title("📁", r.L("PUSH: PAPKALAR", "PUSH: ПАПКИ")), "", card(
        [r.L("Har papka o'z akkauntidan yuboradi. Soni — HAR papkaga (150 = har birida 150).",
             "Каждая папка шлёт со своего аккаунта. Количество — НА КАЖДУЮ папку (150 = по 150).")])), kb(*rows)


async def folder_card(ctx, r: Req):
    db = ctx.db
    fid = int(r.args[0])
    if len(r.args) > 1:
        op = r.args[1]
        f = must(P.folder(db, fid))
        if op == "o":
            P.set_folder(db, fid, push_on=0 if f["push_on"] else 1)
        elif op == "a" and len(r.args) > 2:
            P.set_folder(db, fid, push_account_id=int(r.args[2]) or None)
        elif op == "a":
            btn = [(f"{state_icon(ctx, a['id'])} {a['name']}", f"uf:{fid}:a:{a['id']}")
                   for a in db.all("SELECT * FROM accounts ORDER BY id")]
            btn.append((r.L("✖️ Akkauntsiz", "✖️ Без аккаунта"), f"uf:{fid}:a:0"))
            return title("📲", h(f["name"]), r.L("qaysi akkauntdan?", "с какого аккаунта?")), kb(*grid(btn),
                                                                                              nav(r, f"uf:{fid}"))
        elif op == "n":
            ui.ask(r, "folder_push_n", f"uf:{fid}", fid=fid)
            return title("🔢", h(f["name"])) + "\n\n" + card(
                [r.L("Shu papkaga bir martada nechta? <code>0</code> — umumiy sondan.",
                     "Сколько за раз этой папке? <code>0</code> — общее число.")]), ui.cancel_kb(r, f"uf:{fid}")
        elif op == "q":
            ui.ask(r, "folder_quiet", f"uf:{fid}", fid=fid)
            return title("🌙", h(f["name"])) + "\n\n" + card(
                [r.L("Push YUBORILMAYDIGAN vaqt: <code>21:00 09:00</code>. <code>0</code> — umumiy vaqt.",
                     "Когда НЕ слать Push: <code>21:00 09:00</code>. <code>0</code> — общее время.")]), \
                ui.cancel_kb(r, f"uf:{fid}")
    f = must(P.folder(db, fid))
    quiet = f"{f['quiet_from']}–{f['quiet_to']}" if f["quiet_from"] else r.L("umumiy", "общее")
    lines = [f"📣 Push — {onoff(r, f['push_on'])}",
             f"📲 {r.L('Akkaunt', 'Аккаунт')} — {state_icon(ctx, f['push_account_id'])} {h(acc_name(ctx, f['push_account_id']))}",
             f"🔢 {r.L('Soni', 'Количество')} — <b>{f['push_limit'] or r.L('umumiy', 'общее')}</b>",
             f"🌙 {r.L('Tinch vaqt', 'Тихое время')} — {quiet}"]
    rows = grid([((r.L("⛔ Push o'ch", "⛔ Выкл. Push") if f["push_on"] else r.L("✅ Push yoq", "✅ Вкл. Push")),
                  f"uf:{fid}:o"), (f"📲 {r.L('Akkaunt', 'Аккаунт')}", f"uf:{fid}:a"),
                 (f"🔢 {r.L('Soni', 'Количество')}", f"uf:{fid}:n"), (f"🌙 {r.L('Tinch vaqt', 'Тихое время')}",
                                                                      f"uf:{fid}:q")])
    rows.append(nav(r, "uf"))
    return ui.join(title("📁", h(f["name"]), "Push"), "", card(lines)), kb(*rows)


@on_input("folder_push_n")
async def folder_push_n(ctx, r: Req, fid: int):
    v = parse_number(r.text)
    if v is None or not 0 <= v <= 5000:
        return r.L("⚠️ 0–5000", "⚠️ 0–5000")
    P.set_folder(ctx.db, fid, push_limit=int(v))
    r.args = [str(fid)]
    return await folder_card(ctx, r)


def _quiet(r: Req, text: str):
    raw = text.strip()
    if raw in ("0", "-", ""):
        return "", ""
    parts = re.findall(r"\d{1,2}[:.]\d{2}", raw)
    if len(parts) != 2:
        return None
    try:
        a, b = parse_hhmm(parts[0]), parse_hhmm(parts[1])
    except ValueError:
        return None
    return f"{a.hour:02d}:{a.minute:02d}", f"{b.hour:02d}:{b.minute:02d}"


@on_input("folder_quiet")
async def folder_quiet(ctx, r: Req, fid: int):
    q = _quiet(r, r.text)
    if q is None:
        return r.L("⚠️ Masalan: 21:00 09:00", "⚠️ Например: 21:00 09:00")
    P.set_folder(ctx.db, fid, quiet_from=q[0], quiet_to=q[1])
    r.args = [str(fid)]
    return await folder_card(ctx, r)


# ───────────────────────── jadval
@screen("uj", "full")
async def schedule(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] == "t":
        db.toggle("push_auto")
    lines = [f"⏰ {r.L('Avtomat Push', 'Авто-Push')} — {onoff(r, db.flag('push_auto'))}",
             f"🕒 {r.L('Vaqtlar', 'Время')} — <b>{', '.join(push_times(db)) or '—'}</b>",
             r.L("1-vaqt: hamma lidlar · o'rtadagi: bugun yozganlar oldinda · oxirgisi: faqat bugun yozganlar.",
                 "1-е время: все лиды · среднее: сегодняшние вперёд · последнее: только сегодняшние.")]
    if db.get("push_auto_last"):
        lines.append(r.L("Oxirgisi: ", "Последний: ") + h(db.get("push_auto_last")))
    rows = [[((r.L("⛔ Avtomatni o'chirish", "⛔ Выключить авто") if db.flag("push_auto") else
               r.L("✅ Avtomatni yoqish", "✅ Включить авто")), "uj:t")],
            [(r.L("🕒 Vaqtlarni o'zgartirish", "🕒 Изменить время"), "ujt")], nav(r, "u")]
    return ui.join(title("⏰", r.L("PUSH JADVALI", "РАСПИСАНИЕ PUSH")), "", card(lines)), kb(*rows)


@screen("ujt", "full")
async def schedule_ask(ctx, r: Req):
    ui.ask(r, "push_times", "uj")
    return title("🕒", r.L("VAQTLAR", "ВРЕМЯ")) + "\n\n" + card(
        [r.L("Vaqtlarni yuboring, masalan <code>10:30 15:00 20:00</code>.",
             "Пришлите время, например <code>10:30 15:00 20:00</code>.")]), ui.cancel_kb(r, "uj")


@on_input("push_times")
async def schedule_set(ctx, r: Req):
    parts = re.findall(r"\d{1,2}[:.]\d{2}", r.text)
    good = []
    for p in parts:
        try:
            t = parse_hhmm(p)
            good.append(f"{t.hour:02d}:{t.minute:02d}")
        except ValueError:
            pass
    if not good:
        return r.L("⚠️ Masalan: 10:30 15:00 20:00", "⚠️ Например: 10:30 15:00 20:00")
    ctx.db.set("push_times", ",".join(sorted(set(good))))
    r.args = []
    return await schedule(ctx, r)


# ───────────────────────── sozlamalar
@screen("uo", "full")
async def settings(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] == "speed":
        order = ["slow", "normal", "fast"]
        cur = db.get("push_speed") if db.get("push_speed") in order else "normal"
        db.set("push_speed", order[(order.index(cur) + 1) % 3])
    speeds = SPEED_RU if r.lang == "ru" else SPEED_UZ
    per = f"{db.get('push_from') or db.get('track_from') or '—'} — {db.get('push_to') or r.L('bugun', 'сегодня')}"
    quiet = f"{db.get('push_quiet_from')}–{db.get('push_quiet_to')}" if db.get("push_quiet_from") else "—"
    mins = r.L("daq", "мин")
    lines = [f"🔢 {r.L('Har papkaga', 'На каждую папку')} — <b>{db.get('push_limit')}</b>",
             f"📅 {r.L('Lidlar davri', 'Период лидов')} — {h(per)}",
             f"⚡ {r.L('Tezlik', 'Скорость')} — {speeds.get(db.get('push_speed'), db.get('push_speed'))}",
             f"🆕 {r.L('Yangi lidga yo‘q', 'Новым лидам нет')} — {db.get('push_newlead_minutes')} {mins}",
             f"💬 {r.L('Yaqinda yozishganlarga yo‘q', 'Недавно писавшим нет')} — {db.get('push_idle_minutes')} {mins}",
             f"🔁 {r.L('Qayta yubormaslik', 'Не повторять')} — {db.get('push_repeat_minutes')} {mins}",
             f"🌙 {r.L('Umumiy tinch vaqt', 'Общее тихое время')} — {quiet}",
             f"🔥 {r.L('Faqat shu belgili', 'Только с иконкой')} — {h(db.get('push_emojis') or r.L('hammasi', 'все'))}",
             f"🚫 {r.L('Chiqarilgan', 'Исключены')} — {h(db.get('skip_emojis'))}"]
    btn = [(f"🔢 {r.L('Soni', 'Количество')}", "uoi:push_limit"), (f"📅 {r.L('Davr', 'Период')}", "uoi:period"),
           (f"⚡ {r.L('Tezlik', 'Скорость')}", "uo:speed"), (f"🆕 {r.L('Yangi lid', 'Новый лид')}", "uoi:push_newlead_minutes"),
           (f"💬 {r.L('Yaqinda yozgan', 'Недавно писали')}", "uoi:push_idle_minutes"),
           (f"🔁 {r.L('Takror', 'Повтор')}", "uoi:push_repeat_minutes"),
           (f"🌙 {r.L('Tinch vaqt', 'Тихое время')}", "uoi:quiet"), (f"🔥 {r.L('Belgilar', 'Иконки')}", "uoi:push_emojis"),
           (f"🚫 {r.L('Chiqarilgan', 'Исключены')}", "uoi:skip_emojis")]
    return ui.join(title("⚙️", r.L("PUSH SOZLAMALARI", "НАСТРОЙКИ PUSH")), "", card(lines)), kb(*grid(btn), nav(r, "u"))


PROMPTS = {
    "push_limit": ("Har papkaga bir martada nechta? <code>0</code> — hammasi.", "Сколько за раз на папку? <code>0</code> — все."),
    "period": ("Davr: <code>26.08.2026 14.10.2026</code> yoki bitta sana (o'sha kundan). <code>*</code> — tozalash.",
               "Период: <code>26.08.2026 14.10.2026</code> или одна дата (с неё). <code>*</code> — сброс."),
    "push_newlead_minutes": ("Yangi lidga necha daqiqa Push yubormaslik? (<code>60</code>, <code>2 soat</code>)",
                             "Сколько минут не слать новым лидам? (<code>60</code>, <code>2ч</code>)"),
    "push_idle_minutes": ("Oxirgi xabardan necha daqiqa o'tmaguncha yozmaslik? <code>0</code> — tekshirmaslik.",
                          "Сколько минут после последнего сообщения не писать? <code>0</code> — не проверять."),
    "push_repeat_minutes": ("Push olganlarga necha daqiqa qayta yubormaslik? (kamida 180)",
                            "Сколько минут не слать повторно? (минимум 180)"),
    "quiet": ("Push yuborilmaydigan umumiy vaqt: <code>21:00 09:00</code>. <code>0</code> — yo'q.",
              "Общее время без Push: <code>21:00 09:00</code>. <code>0</code> — нет."),
    "push_emojis": ("Faqat shu belgili lidlarga (masalan <code>🔥</code>). <code>*</code> — hammasiga.",
                    "Только лидам с иконкой (например <code>🔥</code>). <code>*</code> — всем."),
    "skip_emojis": ("Chiqarilgan belgilar (zaderjka va Push'da hisobga olinmaydi), masalan <code>⚡ 💊</code>.",
                    "Исключённые иконки (не учитываются в задержках и Push), например <code>⚡ 💊</code>."),
}


@screen("uoi", "full")
async def setting_ask(ctx, r: Req):
    key = r.args[0]
    ui.ask(r, "push_setting", "uo", key=key)
    uz, ru = PROMPTS[key]
    return title("⚙️", r.L("SOZLAMA", "НАСТРОЙКА")) + "\n\n" + card([r.L(uz, ru)]), ui.cancel_kb(r, "uo")


@on_input("push_setting")
async def setting_set(ctx, r: Req, key: str):
    db, text = ctx.db, r.text.strip()
    if key == "push_limit":
        v = parse_number(text)
        if v is None or not 0 <= v <= 5000:
            return r.L("⚠️ 0–5000", "⚠️ 0–5000")
        db.set(key, str(int(v)))
    elif key == "period":
        if text in ("*", "0", "-"):
            db.set("push_from", "")
            db.set("push_to", "")
        else:
            found = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}", text)
            try:
                a = parse_date(found[0]) if found else None
                b = parse_date(found[1]) if len(found) > 1 else None
            except ValueError:
                a = None
            if a is None:
                return r.L("⚠️ Masalan: 26.08.2026 14.10.2026", "⚠️ Например: 26.08.2026 14.10.2026")
            db.set("push_from", a.isoformat())
            db.set("push_to", b.isoformat() if b else "")
    elif key in ("push_newlead_minutes", "push_idle_minutes", "push_repeat_minutes"):
        try:
            v = parse_minutes(text)
        except ValueError:
            return r.L("⚠️ Masalan: 60 yoki 2 soat", "⚠️ Например: 60 или 2ч")
        if key == "push_repeat_minutes":
            v = max(180, v)
        db.set(key, str(v))
    elif key == "quiet":
        q = _quiet(r, text)
        if q is None:
            return r.L("⚠️ Masalan: 21:00 09:00", "⚠️ Например: 21:00 09:00")
        db.set("push_quiet_from", q[0])
        db.set("push_quiet_to", q[1])
    elif key in ("push_emojis", "skip_emojis"):
        db.set(key, "" if text in ("*", "0", "-") else " ".join(ch for ch in text if not ch.isspace() and ch != ","))
    r.args = []
    return await settings(ctx, r)


# ───────────────────────── jurnal
@screen("uh", "full")
async def history(ctx, r: Req):
    rows = ctx.db.all("SELECT * FROM broadcasts ORDER BY id DESC LIMIT 12")
    names = {"done": "✅", "stopped": "⏹", "aborted": "⛔", "interrupted": "⚠️", "running": "⏳"}
    lines = [f"{names.get(b['status'], b['status'])} {fmt(b['started_ts'], ctx.tz)} · "
             f"{'⏰' if b['trigger'] == 'auto' else '👆'} · <b>{b['sent']}</b>/{b['total']}"
             + (f" · ✖️{b['failed']}" if b["failed"] else "") for b in rows]
    return ui.join(title("🧾", r.L("PUSH JURNALI", "ЖУРНАЛ PUSH")), "",
                   card(lines) if lines else r.L("<i>Hozircha bo'sh.</i>", "<i>Пока пусто.</i>")), kb(nav(r, "u"))
