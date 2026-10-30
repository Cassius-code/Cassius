"""📣 Push: matn/media, papkalar (akkaunt, soni), sozlamalar, yuborish (soatga qarab tartib), jurnal."""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime

from . import people as P
from . import push_lib as L
from . import ui
from .timeutil import fmt, parse_date, parse_minutes, parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title, must

log = logging.getLogger("panel_push")

MAX_MEDIA = 20 * 1024 * 1024
SLOT_BTN = {"morning": ("🌅 Ertalabkiga o'tish", "🌅 Переключить на утренний"),
            "day": ("☀️ Kunduzgiga o'tish", "☀️ Переключить на дневной"),
            "evening": ("🌙 Kechkiga o'tish", "🌙 Переключить на вечерний")}
SLOT_ICON = {"morning": "🌅", "day": "☀️", "evening": "🌙"}
SPEED_UZ = {"fast": "tez 1–2 s", "normal": "oddiy 2–3 s", "slow": "ehtiyot 3–5 s"}
SPEED_RU = {"fast": "быстро 1–2 с", "normal": "обычно 2–3 с", "slow": "осторожно 3–5 с"}
KIND_UZ = {"voice": "🎤 ovozli", "video_note": "⭕ dumaloq video", "video": "🎬 video", "photo": "🖼 rasm",
           "audio": "🎵 audio", "animation": "🎞 gif", "document": "📄 fayl"}
KIND_RU = {"voice": "🎤 голосовое", "video_note": "⭕ кружок", "video": "🎬 видео", "photo": "🖼 фото",
           "audio": "🎵 аудио", "animation": "🎞 gif", "document": "📄 файл"}


def acc_name(ctx, acc_id) -> str:
    from .accounts import MAIN
    from .context import tr
    if acc_id == MAIN:
        return "🔑 " + tr("Asosiy akkaunt", "Основной аккаунт")
    a = ctx.db.one("SELECT name FROM accounts WHERE id=?", (acc_id,)) if acc_id else None
    return a["name"] if a else "—"


def used_by(ctx, acc_id, except_fid: int = 0) -> str:
    """Akkaunt yana qaysi papkalarda Push qiladi (bitta akkaunt 2–3 papkada bo'lishi mumkin)."""
    names = [f["name"] for f in P.folders(ctx.db) if f["push_account_id"] == acc_id and f["id"] != except_fid]
    return (" · " + ", ".join(names))[:30] if names else ""


def state_icon(ctx, acc_id) -> str:
    from .push import spam_limited
    if acc_id and spam_limited(ctx.db, acc_id):
        return "🚫"                                        # @SpamBot: spam-cheklov — Push bu akkauntdan ketmaydi
    st = ctx.pool.state_of(acc_id) if ctx.pool else "no_session"
    return {"online": "🟢", "connecting": "🟡", "starting": "🟡", "paused": "⏸"}.get(st, "🔴")


def dstr(iso: str) -> str:
    try:
        return parse_date(iso).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso or "—"


def slot_info(ctx, r: Req, slot: str) -> tuple[str, str]:
    """(nom, qoida) — tanlangan Push turi uchun (egasi tugma bilan tanlaydi, soatga qaralmaydi)."""
    idle = ctx.db.get_int("push_idle_minutes")
    if slot == "morning":
        return (r.L("🌅 Ertalabki push", "🌅 Утренний push"),
                r.L("Bugun gaplashmaganlarga: kecha yozganlardan boshlab eskiroqlariga (lidning oxirgi yozgani "
                    "bo'yicha, yangisi oldin).",
                    "Тем, с кем сегодня не общались: со вчерашних — к более старым (по последнему сообщению лида, "
                    "новые раньше)."))
    head = r.L("🌙 Kechki push", "🌙 Вечерний push") if slot == "evening" else r.L("☀️ Kunduzgi push", "☀️ Дневной push")
    return (head,
            r.L(f"Avval bugun gaplashganlar: 1) ertalab gaplashganlar, 2) {idle} daq dan beri jim turganlar; ular "
                "tugasa — kechagi, keyin eskiroqlar. Hozir gaplashayotganlarga yuborilmaydi.",
                f"Сначала сегодняшние: 1) утренние, 2) молчат {idle}+ мин; потом вчерашние и старше. Тем, кто "
                "сейчас в переписке, — не отправляется."))


def current_lines(ctx, r: Req) -> list[str]:
    """📚 Hozirgi Push: bot bergan nom, matn boshi, media, nechta lid olgan."""
    cur = ctx.pusher.current()
    if cur is None:
        return [r.L("<i>Push yo'q — «🆕 Yangi Push» bosing yoki matn yozing.</i>",
                    "<i>Пуша нет — нажмите «🆕 Новый Пуш» или напишите текст.</i>")]
    text = (cur["text"] or "").strip()
    media = L.media_of(cur)
    kinds = KIND_RU if r.lang == "ru" else KIND_UZ
    preview = h(text[:140]) + ("…" if len(text) > 140 else "") if text else r.L("<i>matn yo'q</i>", "<i>нет текста</i>")
    got = L.got_count(ctx.db, cur["id"])
    out = [f"<b>📚 {h(L.label(cur, r.lang, ctx.tz))}</b>" + (f" <i>({h(cur['note'])})</i>" if cur["note"] else ""),
           preview]
    if media:
        out.append(f"📎 {kinds.get(media['kind'], media['kind'])}")
    out.append(r.L(f"Olgan: <b>{got}</b> ta lid — ularga bu Push boshqa ketmaydi",
                   f"Получили: <b>{got}</b> лидов — им этот Пуш больше не уйдёт"))
    return out


@screen("u", "full")
async def push_menu(ctx, r: Req):
    ui.view(r, "u")                                        # jonli yangilanadi (raqamlar shu yerda)
    db, pu = ctx.db, ctx.pusher
    plan = []
    for f in P.folders(db):
        if not f["push_on"]:
            continue
        n = f["push_limit"] or db.get_int("push_limit")
        plan.append(f"📁 {h(f['name'])} → {state_icon(ctx, f['push_account_id'])} {h(acc_name(ctx, f['push_account_id']))}"
                    f" · <b>{n or r.L('hammasi', 'все')}</b>")
    base = db.get("push_base_from") or "2026-08-28"
    parts = [title("📣", r.L("PUSH", "ПУШ"), r.L("issiq lidlarga xabar", "сообщение горячим лидам")), "",
             card(current_lines(ctx, r)),
             card([f"<b>{r.L('Papkalar', 'Папки')}</b>"] + (plan or [r.L("Push yoqilgan papka yo'q", "Нет папок с Пушем")]) +
                  [f"📅 {r.L('Baza', 'База')}: {dstr(base)} {r.L('dan keyin o‘zi yozgan lidlar', 'и позже (писали сами)')}" +
                   base_state(ctx, r)] + ([r.L("🧪 Haqiqiy ta'sir — yoqiq (har 10 lidning 1 tasi — nazorat)",
                                              "🧪 Истинный эффект — вкл (каждый 10-й лид — контроль)")]
                                         if db.flag("push_control") else []))]
    if pu.running:
        parts.append(card([f"⏳ {r.L('Yuborilmoqda', 'Идёт рассылка')} — <b>{h(pu.progress_text or '…')}</b>",
                           r.L("<i>Raqamlar shu yerda o'zi yangilanadi. Menyuga o'tsangiz ham Push davom etadi.</i>",
                               "<i>Цифры обновляются здесь сами. Можно уйти в меню — рассылка продолжится.</i>")]))
    elif pu.last_report:
        ts, res = pu.last_report
        parts.append(card([f"{report_lines(ctx, r, res)[0]} · {datetime.fromtimestamp(ts, ctx.tz):%d.%m %H:%M}"]
                          + report_lines(ctx, r, res)[1:]))
    rows = []
    if pu.running:
        rows.append([(r.L("⏹ To'xtatish", "⏹ Остановить"), "ux")])
    else:
        cont = pu.continuable()
        if cont:                                           # oxirgi Push bitmay qolgan — faqat qolganini yuborish
            rows.append([(r.L(f"▶️ Davom ettirish — qolgan {cont[1]} ta", f"▶️ Продолжить — осталось {cont[1]}"),
                          "uc")])
        rows.append([(r.L("🌅 Ertalabki", "🌅 Утренний"), "us:morning"), (r.L("☀️ Kunduzgi", "☀️ Дневной"), "us:day"),
                     (r.L("🌙 Kechki", "🌙 Вечерний"), "us:evening")])
        rows.append([(r.L("🧪 Test (o'zimga)", "🧪 Тест (себе)"), "ut")])
    rows += grid([(r.L("✏️ Matn", "✏️ Текст"), "ue"), (r.L("📎 Media", "📎 Медиа"), "um"),
                  (r.L("📚 Kutubxona", "📚 Библиотека"), "ul"), (r.L("🆕 Yangi Push", "🆕 Новый Пуш"), "un"),
                  (r.L("📁 Papkalar", "📁 Папки"), "uf"), (r.L("⚙️ Sozlamalar", "⚙️ Настройки"), "uo"),
                  (r.L("🧾 Natija", "🧾 Результат"), "uh")])
    rows.append(nav(r))
    return ui.join(*parts), kb(*rows)


# ───────────────────────── yuborish
@screen("us", "full")
async def start_preview(ctx, r: Req):
    pu = ctx.pusher
    if not pu.has_content():
        return r.L("⚠️ Avval matn yoki media qo'shing", "⚠️ Сначала добавьте текст или медиа")
    slot = r.args[0] if r.args and r.args[0] in SLOT_BTN else "day"
    aud = pu.audience(slot)
    n = len(aud["items"])
    folders = {f["id"]: f for f in P.folders(ctx.db)}
    name, rule = slot_info(ctx, r, slot)
    g = aud["groups"]
    order = {"morning": [(r.L("kecha yozganlar", "вчерашние"), g["yesterday"]), (r.L("eskiroqlar", "старше"), g["older"])],
             "day": [(r.L("ertalab gaplashganlar", "утренние"), g["morning"]), (r.L("jim turganlar", "молчат"), g["quiet"]),
                     (r.L("kechagilar", "вчерашние"), g["yesterday"]), (r.L("eskiroqlar", "старше"), g["older"])]}
    order["evening"] = order["day"]
    steps = [f"{i + 1}) {a} — <b>{b}</b>" for i, (a, b) in enumerate(order[slot])]
    lines = [f"📁 {h(folders[fid]['name'])} → <b>{q}</b>" for fid, q in aud["by_folder"].items() if q]
    skipped = [(r.L("shu Push'ni oldin olgan", "уже получали этот Пуш"), aud["got_before"]),
               (r.L("hozir gaplashayotgan", "сейчас в переписке"), aud["cooled"]),
               (r.L("yangi / stavkada", "новые / в ставке"), aud["fresh"]),
               (r.L("3 soat ichida Push olgan", "получали Пуш за 3 ч"), aud["repeated"])]
    sk = ", ".join(f"{a} — {b}" for a, b in skipped if b)
    cur = pu.current()
    info = [f"<b>{name}</b> · 📚 {h(L.label(cur, r.lang, ctx.tz))}", f"<i>{rule}</i>", ""] + steps + [
        "", (r.L(f"Jami: <b>{n}</b> · ≈ {pu.estimate_minutes(n)} daq", f"Всего: <b>{n}</b> · ≈ {pu.estimate_minutes(n)} мин")
             if n else r.L("Hozir yuboriladigan lid yo'q.", "Сейчас некому отправлять."))]
    if sk:
        info.append(r.L("O'tkazildi: ", "Пропущено: ") + sk)
    if ctx.db.flag("push_control"):
        info.append(r.L("🧪 Har 10 lidning 1 tasiga yuborilmaydi (nazorat) — o'rniga boshqasi, son o'zgarmaydi.",
                        "🧪 Каждому 10-му не отправляется (контроль) — вместо него другой, количество то же."))
    if aud["no_account"]:
        info.append("⚠️ " + r.L("Akkauntsiz papkalar: ", "Папки без аккаунта: ") +
                    h(", ".join(folders[f]["name"] for f in aud["no_account"])))
    text = ui.join(title("🚀", r.L("PUSHNI TASDIQLANG", "ПОДТВЕРДИТЕ ПУШ")), "", card(info), card(lines) if lines else "")
    rows = [[(r.L("✅ Boshlash", "✅ Начать"), f"usy:{slot}")]] if n else []
    rows.append([(r.L(uz, ru), f"us:{k}") for k, (uz, ru) in SLOT_BTN.items() if k != slot])
    rows.append(nav(r, "u"))
    return text, kb(*rows)


@screen("uc", "full")
async def continue_run(ctx, r: Req):
    """▶️ Oxirgi Push'ni davom ettirish: faqat yetmay qolgan papkalar, o'z sonigacha (yuborilganlarga qayta yo'q)."""
    pu = ctx.pusher
    if pu.running:
        return r.L("⏳ Push allaqachon ketyapti", "⏳ Рассылка уже идёт")
    import asyncio

    async def job():
        try:
            await pu.continue_last()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Push davomi")

    ui.bg(job())
    await asyncio.sleep(0)
    ui.view(r, "u")
    return await push_menu(ctx, r)


@screen("usy", "full")
async def start_run(ctx, r: Req):
    pu = ctx.pusher
    if pu.running:
        return r.L("⏳ Push allaqachon ketyapti", "⏳ Рассылка уже идёт")
    import asyncio
    slot = r.args[0] if r.args and r.args[0] in SLOT_BTN else "day"

    async def job():
        try:
            await pu.run("manual", slot)                   # holat va natija Pusher'da — panel o'zi ko'rsatadi
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Push")

    ui.bg(job())
    await asyncio.sleep(0)                                 # Push boshlansin — ekranda darhol «ketyapti»
    ui.view(r, "u")
    return await push_menu(ctx, r)


def report_text(ctx, r: Req, res: dict) -> str:
    return ui.join(title("📣", r.L("PUSH", "ПУШ")), "", card(report_lines(ctx, r, res)))


def report_lines(ctx, r: Req, res: dict) -> list[str]:
    names = {"done": r.L("✅ Push tugadi", "✅ Рассылка завершена"), "stopped": r.L("⏹ To'xtatildi", "⏹ Остановлено"),
             "aborted": r.L("⛔ Push uzildi", "⛔ Рассылка прервана"), "busy": r.L("⏳ Boshqa Push ketyapti",
                                                                              "⏳ Другая рассылка идёт"),
             "empty": r.L("⚠️ Matn yo'q", "⚠️ Нет текста"), "disabled": r.L("⛔ Push o'chirilgan", "⛔ Пуш выключен"),
             "interrupted": r.L("⚠️ Qayta ishga tushish sababli uzildi", "⚠️ Прервано перезапуском")}
    lines = [f"<b>{names.get(res['status'], res['status'])}</b>"]
    if "sent" in res:
        sent, total, bad = res["sent"], res["total"], res["failed"]
        lines.append(r.L(f"Yuborildi: <b>{sent}</b> ta", f"Отправлено: <b>{sent}</b>")
                     + (r.L(f" (rejada {total})", f" (план {total})") if total != sent else ""))
        if bad:
            lines.append(r.L(f"Yuborilmadi: <b>{bad}</b> ta", f"Не отправлено: <b>{bad}</b>"))
        if res.get("held"):
            lines.append(r.L(f"🧪 Nazorat guruhi (yuborilmadi, taqqoslash uchun): {res['held']} ta",
                             f"🧪 Контрольная группа (не отправлено, для сравнения): {res['held']}"))
        folders = {f["id"]: f for f in P.folders(ctx.db)}
        for fid, (ok, no) in res.get("per_folder", {}).items():
            if fid in folders:
                lines.append(f"📁 {h(folders[fid]['name'])}: {ok} {r.L('ta', '')}".rstrip()
                             + (r.L(f" · yuborilmadi {no}", f" · не отправлено {no}") if no else ""))
        if res.get("reasons"):
            top = sorted(res["reasons"].items(), key=lambda kv: -kv[1])[:3]
            lines.append(r.L("Nega yuborilmadi: ", "Почему не отправлено: ") +
                         "; ".join(f"{h(reason_text(r, k))} — {v}" for k, v in top))
    return lines


REASONS = [("TopicClosed", "topik yopilgan", "топик закрыт"), ("TopicDeleted", "topik o'chirilgan", "топик удалён"),
           ("ChatWriteForbidden", "yozishga ruxsat yo'q", "нет права писать"),
           ("ChatSendMediaForbidden", "guruhda media taqiqlangan", "в группе запрещены медиа"),
           ("ChatSendVoicesForbidden", "guruhda ovozli xabar taqiqlangan", "в группе запрещены голосовые"),
           ("ChatSendGifsForbidden", "guruhda gif taqiqlangan", "в группе запрещены gif"),
           ("UserBannedInChannel", "akkaunt guruhda bloklangan", "аккаунт заблокирован в группе"),
           ("ChatAdminRequired", "admin huquqi kerak", "нужны права админа"),
           ("PeerIdInvalid", "chat topilmadi", "чат не найден"), ("ValueError", "chat topilmadi", "чат не найден"),
           ("akkaunt tarmoqda emas", "akkaunt ulanmagan", "аккаунт не подключён"),
           ("akkaunt ulanmagan", "akkaunt ulanmagan", "аккаунт не подключён"),
           ("spam-cheklov", "akkauntda spam-cheklov", "у аккаунта спам-ограничение"),
           ("PeerFlood", "Telegram akkauntni chekladi (spam)", "Telegram ограничил аккаунт (спам)"),
           ("media fayli topilmadi", "media fayli topilmadi — qayta yuklang", "файл медиа не найден — загрузите заново")]


def reason_text(r: Req, reason: str) -> str:
    """Yuborilmaslik sababi — oddiy so'z bilan (soniya emas — daqiqa)."""
    m = re.search(r"Telegram (\d+) daq kutishni so'radi \((\d\d:\d\d) gacha\)", reason)
    if m:
        return r.L(f"Telegram {m.group(1)} daqiqa kutishni so'radi ({m.group(2)} gacha)",
                   f"Telegram попросил подождать {m.group(1)} мин (до {m.group(2)})")
    m = re.search(r"FloodWait (\d+)", reason)
    if m:
        mins = (int(m.group(1)) + 59) // 60
        return r.L(f"Telegram {mins} daqiqa kutishni so'radi", f"Telegram попросил подождать {mins} мин")
    for key, uz, ru in REASONS:
        if key in reason:
            return r.L(uz, ru)
    return reason.replace("to'xtatildi: ", "")


@screen("ux", "full")
async def stop(ctx, r: Req):
    ctx.pusher.stop()
    await ctx.pusher.wait_idle(8)                          # to'xtaguncha kutamiz — ekranda darhol «▶️ Davom ettirish»
    ui.view(r, "u")
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


# ───────────────────────── matn va media (📚 hozirgi Push — raqami o'zgarmaydi)
def _cur_or_new(ctx) -> int:
    cur = ctx.pusher.current()
    if cur is not None:
        return cur["id"]
    pid = L.create(ctx.db)
    L.set_current(ctx.db, pid)
    return pid


async def _merged_note(ctx, r: Req, merged: int | None) -> None:
    if not merged:                                         # yuborilgan Push boshqa raqam bilan aynan bir xil bo'lib qoldi
        cur = ctx.pusher.current()
        dup = L.same_as(ctx.db, cur["fp"], cur["id"]) if cur is not None else None
        if dup is not None:
            await ui.toast(ctx.bot, r.chat_id, r.L(
                f"⚠️ №{cur['id']} endi №{dup['id']} bilan aynan bir xil — №{dup['id']} ni olganlarga ham ketishi "
                f"mumkin. Boshqa matn yozing yoki 📚 Kutubxonadan №{dup['id']} ni tanlang.",
                f"⚠️ №{cur['id']} теперь точно как №{dup['id']} — может уйти и тем, кто получил №{dup['id']}. "
                f"Напишите другой текст или выберите №{dup['id']} в 📚 Библиотеке."), 10)
        return
    if merged:
        got = L.got_count(ctx.db, merged)
        await ui.toast(ctx.bot, r.chat_id, r.L(f"📚 Bu №{merged} bilan aynan bir xil — №{merged} deb olindi "
                                               f"({got} ta lid olgan, ularga ketmaydi)",
                                               f"📚 Это точно как №{merged} — считается №{merged} "
                                               f"(получили {got}, им не уйдёт)"), 8)


@screen("ue", "full")
async def text_ask(ctx, r: Req):
    ui.ask(r, "push_text", "u")
    cur = ctx.pusher.current()
    note = (r.L(f"Hozirgi: <b>{h(L.label(cur, r.lang, ctx.tz))}</b> — raqami o'zgarmaydi. Yangi raqam kerak bo'lsa — "
                "«🆕 Yangi Push».", f"Текущий: <b>{h(L.label(cur, r.lang, ctx.tz))}</b> — номер не меняется. Нужен новый "
                "номер — «🆕 Новый Пуш».") if cur is not None else "")
    return title("✏️", r.L("PUSH MATNI", "ТЕКСТ ПУША")) + "\n\n" + card(
        [x for x in (note, r.L("Matnni yuboring (3500 belgigacha). <code>-</code> — matnni olib tashlash.",
                               "Пришлите текст (до 3500 символов). <code>-</code> — убрать текст.")) if x]), \
        ui.cancel_kb(r, "u")


@on_input("push_text")
async def text_set(ctx, r: Req):
    text = r.message.text if r.message is not None and r.message.text else r.text
    if text.strip() in ("-", "—"):
        text = ""
    elif len(text) > 3500:
        return r.L("⚠️ 3500 belgidan oshmasin", "⚠️ Не больше 3500 символов")
    _pid, merged = L.update(ctx.db, _cur_or_new(ctx), text=text)
    await _merged_note(ctx, r, merged)
    return await push_menu(ctx, r)


def extract_media(message):
    if message.voice:
        return "voice", message.voice.file_id, message.voice.file_size, ".ogg", message.voice.file_unique_id
    if message.video_note:
        v = message.video_note
        return "video_note", v.file_id, v.file_size, ".mp4", v.file_unique_id
    if message.video:
        return "video", message.video.file_id, message.video.file_size, ".mp4", message.video.file_unique_id
    if message.animation:
        a = message.animation
        return "animation", a.file_id, a.file_size, ".mp4", a.file_unique_id
    if message.photo:
        ph = message.photo[-1]
        return "photo", ph.file_id, ph.file_size, ".jpg", ph.file_unique_id
    if message.audio:
        return "audio", message.audio.file_id, message.audio.file_size, ".mp3", message.audio.file_unique_id
    if message.document:
        d = message.document
        return "document", d.file_id, d.file_size, (os.path.splitext(d.file_name or "")[1][:8] or ".bin"), d.file_unique_id
    return None


@screen("um", "full")
async def media_ask(ctx, r: Req):
    ui.ask(r, "push_media", "u")
    rows = [[(r.L("🗑 Mediani olib tashlash", "🗑 Убрать медиа"), "umx")]] if ctx.pusher.media() else []
    rows.append([(r.L("✖️ Bekor qilish", "✖️ Отмена"), "u")])
    return title("📎", r.L("PUSH MEDIASI", "МЕДИА ПУША")) + "\n\n" + card(
        [r.L("Yuboring: 🎤 ovozli, ⭕ dumaloq video, 🎬 video, 🖼 rasm yoki fayl (20 MB gacha). Matn izoh bo'lib ketadi.",
             "Пришлите: 🎤 голосовое, ⭕ кружок, 🎬 видео, 🖼 фото или файл (до 20 МБ). Текст пойдёт подписью."),
         r.L("<i>Eski Push'ni qaytarmoqchi bo'lsangiz — o'sha xabarni forward qiling: bot uni eski raqam deb taniydi. "
             "Ovozni qayta yozsangiz yoki videoni galereyadan qayta yuklasangiz — bu yangi fayl, bot uni yangi Push "
             "(yangi raqam) deb biladi.</i>",
             "<i>Хотите вернуть старый Пуш — перешлите то же сообщение: бот узнает старый номер. Если перезаписать "
             "голосовое или заново загрузить видео из галереи — это новый файл, бот считает его новым Пушем "
             "(новый номер).</i>")]), \
        kb(*rows)


@screen("umx", "full")
async def media_remove(ctx, r: Req):
    cur = ctx.pusher.current()
    if cur is not None:
        old = L.media_of(cur)
        _pid, merged = L.update(ctx.db, cur["id"], media=None)
        drop_media(ctx, old)
        await _merged_note(ctx, r, merged)
    ui.view(r, "u")
    return await push_menu(ctx, r)


def drop_media(ctx, media) -> None:
    """Fayl boshqa hech bir Push'da ishlatilmasa — o'chiriladi."""
    if not media or not media.get("path"):
        return
    if media["path"] not in L.media_paths(ctx.db):
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
    kind, file_id, size, ext, uid = found
    if size and size > MAX_MEDIA:
        return r.L("⚠️ 20 MB dan katta", "⚠️ Больше 20 МБ")
    folder = os.path.join(str(ctx.cfg.data_dir), "push_media")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    try:
        await ctx.bot.download(file_id, destination=path)
    except Exception as exc:
        return r.L(f"⚠️ Yuklab bo'lmadi ({type(exc).__name__})", f"⚠️ Не удалось скачать ({type(exc).__name__})")
    pid = _cur_or_new(ctx)
    old = L.media_of(L.get(ctx.db, pid))
    media = {"kind": kind, "file_id": file_id, "path": path, "uid": uid, "sha": L.file_sha(path)}
    new_pid, merged = L.update(ctx.db, pid, media=media)
    if merged:
        drop_media(ctx, media)                         # eski raqamning o'z fayli bor — yangi nusxa kerak emas
    drop_media(ctx, old)
    await _merged_note(ctx, r, merged)
    return await push_menu(ctx, r)


# ───────────────────────── 📚 kutubxona (har Push — raqam; bot nom beradi)
@screen("ul", "full")
async def library(ctx, r: Req):
    db = ctx.db
    a = r.args
    if len(a) >= 2 and a[0] == "s" and a[1].isdigit() and L.get(db, int(a[1])) is not None:
        L.set_current(db, int(a[1]))
        await ui.toast(ctx.bot, r.chat_id, r.L(f"✅ №{a[1]} — hozirgi Push", f"✅ №{a[1]} — текущий Пуш"))
        ui.view(r, "u")
        return await push_menu(ctx, r)
    if len(a) >= 2 and a[0] == "a" and a[1].isdigit():
        row = L.get(db, int(a[1]))
        if row is not None:
            db.run("UPDATE pushes SET archived=? WHERE id=?", (0 if row["archived"] else 1, row["id"]))
        ui.view(r, "ul:all" if "all" in a else "ul")
    show_all = "all" in a
    cur = ctx.pusher.current()
    rows = []
    for p in db.all("SELECT * FROM pushes " + ("" if show_all else "WHERE archived=0 ") + "ORDER BY id DESC LIMIT 30"):
        mark = "✅ " if cur is not None and cur["id"] == p["id"] else ("🗄 " if p["archived"] else "")
        got = L.got_count(db, p["id"])
        rows.append([(f"{mark}{L.label(p, r.lang, ctx.tz)} · 👥 {got}"[:60], f"ul:s:{p['id']}"),
                     ("♻️" if p["archived"] else "🗄", f"ul:a:{p['id']}" + (":all" if show_all else ""))])
    rows.append([(r.L("🆕 Yangi Push", "🆕 Новый Пуш"), "un"),
                 (r.L("🗄 Arxivdagilar", "🗄 Архив") if not show_all else r.L("📚 Faqat faollar", "📚 Только активные"),
                  "ul:all" if not show_all else "ul")])
    rows.append(nav(r, "u"))
    note = r.L("Har Push — raqam. Nomni bot beradi (№ · turi · sana). 👥 — nechta lid olgan: bitta raqam bitta lidga "
               "hech qachon ikki marta ketmaydi. Bosing — shu Push yuboriladigan bo'ladi. 🗄 — arxivga (yashirish).",
               "Каждый Пуш — номер. Имя даёт бот (№ · тип · дата). 👥 — сколько лидов получили: один номер одному лиду "
               "никогда дважды. Нажмите — этот Пуш станет текущим. 🗄 — в архив (скрыть).")
    return ui.join(title("📚", r.L("PUSH KUTUBXONASI", "БИБЛИОТЕКА ПУШЕЙ")), "", card([note])), kb(*rows)


@screen("un", "full")
async def new_push(ctx, r: Req):
    """🆕 Yangi raqam: bo'sh Push yaratiladi va hozirgi bo'ladi — keyin matn yoki media yuboriladi."""
    db = ctx.db
    cur = ctx.pusher.current()
    if cur is not None and not L.has_content(cur) and not L.sent_ever(db, cur["id"]):
        pid = cur["id"]                                    # bo'sh Push allaqachon bor — yangisi shart emas
    else:
        pid = L.create(db, ts=int(ctx.clock()))
        L.set_current(db, pid)
    await ui.toast(ctx.bot, r.chat_id, r.L(f"🆕 №{pid} — endi matn yoki media yuboring",
                                           f"🆕 №{pid} — теперь пришлите текст или медиа"), 6)
    ui.view(r, "u")
    return await push_menu(ctx, r)


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
    return ui.join(title("📁", r.L("PUSH: PAPKALAR", "ПУШ: ПАПКИ")), "", card(
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
            from .accounts import MAIN
            btn = [(f"{state_icon(ctx, MAIN)} {acc_name(ctx, MAIN)}{used_by(ctx, MAIN, fid)}"[:60], f"uf:{fid}:a:{MAIN}")]
            btn += [(f"{state_icon(ctx, a['id'])} {a['name']} {a['label']}{used_by(ctx, a['id'], fid)}"[:60],
                     f"uf:{fid}:a:{a['id']}") for a in db.all("SELECT * FROM accounts ORDER BY id")]
            btn.append((r.L("➕ Yangi akkaunt ulash", "➕ Подключить новый"), f"sml:push:{fid}"))
            btn.append((r.L("✖️ Akkauntsiz", "✖️ Без аккаунта"), f"uf:{fid}:a:0"))
            return ui.join(title("📲", h(f["name"]), r.L("qaysi akkauntdan?", "с какого аккаунта?")), "", card(
                [r.L("Bitta akkaunt 2–3 papkaga ham bo'ladi: navbat bilan, odatdagi tezlikda yuboradi. "
                     "🔑 Asosiy akkaunt ham tanlanishi mumkin.",
                     "Один аккаунт можно на 2–3 папки: отправит по очереди с обычной скоростью. "
                     "Можно выбрать и 🔑 основной аккаунт.")])), kb(*grid(btn, 1), nav(r, f"uf:{fid}"))
        elif op == "n":
            ui.ask(r, "folder_push_n", f"uf:{fid}", fid=fid)
            return title("🔢", h(f["name"])) + "\n\n" + card(
                [r.L("Shu papkaga bir martada nechta? <code>0</code> — umumiy sondan.",
                     "Сколько за раз этой папке? <code>0</code> — общее число.")]), ui.cancel_kb(r, f"uf:{fid}")
        ui.view(r, f"uf:{fid}")
    f = must(P.folder(db, fid))
    lines = [f"📣 {r.L('Push', 'Пуш')} — {onoff(r, f['push_on'])}",
             f"📲 {r.L('Akkaunt', 'Аккаунт')} — {state_icon(ctx, f['push_account_id'])} {h(acc_name(ctx, f['push_account_id']))}",
             f"🔢 {r.L('Soni', 'Количество')} — <b>{f['push_limit'] or r.L('umumiy', 'общее')}</b>"]
    rows = grid([((r.L("⛔ Push'ni o'chirish", "⛔ Выкл. Пуш") if f["push_on"] else r.L("✅ Push'ni yoqish", "✅ Вкл. Пуш")),
                  f"uf:{fid}:o"), (f"📲 {r.L('Akkaunt', 'Аккаунт')}", f"uf:{fid}:a"),
                 (f"🔢 {r.L('Soni', 'Количество')}", f"uf:{fid}:n")])
    rows.append(nav(r, "uf"))
    return ui.join(title("📁", h(f["name"]), r.L("Push", "Пуш")), "", card(lines)), kb(*rows)


@on_input("folder_push_n")
async def folder_push_n(ctx, r: Req, fid: int):
    v = parse_number(r.text)
    if v is None or not 0 <= v <= 5000:
        return r.L("⚠️ 0–5000", "⚠️ 0–5000")
    P.set_folder(ctx.db, fid, push_limit=int(v))
    r.args = [str(fid)]
    return await folder_card(ctx, r)


@screen("uo", "full")
async def settings(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] == "speed":
        order = ["slow", "normal", "fast"]
        cur = db.get("push_speed") if db.get("push_speed") in order else "normal"
        db.set("push_speed", order[(order.index(cur) + 1) % 3])
        ui.view(r, "uo")
    if r.args and r.args[0] == "grp":
        db.set("push_group", "0" if db.flag("push_group") else "1")
        ui.view(r, "uo")
    if r.args and r.args[0] == "ctl":
        db.set("push_control", "0" if db.flag("push_control") else "1")
        ui.view(r, "uo")
    speeds = SPEED_RU if r.lang == "ru" else SPEED_UZ
    mins = r.L("daq", "мин")
    lines = [f"🔢 {r.L('Har papkaga', 'На каждую папку')} — <b>{db.get('push_limit')}</b> "
             f"<i>({r.L('aynan shuncha', 'ровно столько')})</i>",
             f"⚡ {r.L('Tezlik', 'Скорость')} — {speeds.get(db.get('push_speed'), db.get('push_speed'))}",
             f"🌅/☀️ {r.L('Turi — 📣 menyuda tugma bilan (soatga qaramaydi)', 'Тип — кнопкой в 📣 меню (не по часам)')}",
             f"⏳ {r.L('Jim turgan deb hisoblash', 'Считать «молчит»')} — {db.get_int('push_idle_minutes')} {mins}",
             f"📅 {r.L('Baza', 'База')} — {dstr(db.get('push_base_from') or '2026-08-28')} "
             f"{r.L('dan keyin o‘zi yozgan lidlar (yangi ham, eski ham)', 'и позже: писали сами (новые и старые)')}"
             f"{base_state(ctx, r)}",
             f"🗓 {r.L('Davr', 'Период')} — {period_text(ctx, r)}",
             f"🆕 {r.L('Yangi lidga yo‘q', 'Новым лидам нет')} — {db.get('push_newlead_minutes')} {mins}",
             f"🔁 {r.L('Qayta yubormaslik', 'Не повторять')} — {db.get('push_repeat_minutes')} {mins}",
             f"🔥 {r.L('Faqat shu belgili', 'Только с иконкой')} — {h(db.get('push_emojis') or r.L('hammasi', 'все'))}",
             f"🚫 {r.L('Chiqarilgan', 'Исключены')} — {h(db.get('skip_emojis'))}",
             f"👥 {r.L('«Проёб»da Push paneli', 'Панель Пуша в «Проёб»')} — "
             f"{r.L('🟢 yoqiq', '🟢 вкл') if db.flag('push_group') else r.L('⚪ o‘chiq', '⚪ выкл')}",
             f"🧪 {r.L('Haqiqiy ta‘sir', 'Истинный эффект')} — "
             f"{r.L('🟢 yoqiq', '🟢 вкл') if db.flag('push_control') else r.L('⚪ o‘chiq', '⚪ выкл')}",
             r.L("<i>🧪 yoqilsa: har 10 lidning 1 tasiga Push yuborilmaydi (o'rniga boshqasi — son o'zgarmaydi). "
                 "🧾 Natijada ko'rinadi: Push olganlar javob yozdimi va olmaganlar o'zi yozdimi — Push haqiqatan "
                 "qancha foyda beryapti.</i>",
                 "<i>🧪 если вкл: каждому 10-му лиду Пуш не отправляется (вместо него другой — количество то же). "
                 "В 🧾 Результате видно: ответили ли получившие и написали ли сами не получившие — сколько реально "
                 "даёт Пуш.</i>")]
    btn = [(f"🔢 {r.L('Soni', 'Количество')}", "uoi:push_limit"), (f"⚡ {r.L('Tezlik', 'Скорость')}", "uo:speed"),
           (f"⏳ {r.L('Jim turgan', 'Молчит')}", "uoi:push_idle_minutes"),
           (f"🧪 {r.L('Haqiqiy ta‘sir', 'Истинный эффект')}", "uo:ctl"),
           (f"🗓 {r.L('Davr', 'Период')}", "upd"),
           (f"📅 {r.L('Baza', 'База')}", "uoi:push_base_from"), (f"🆕 {r.L('Yangi lid', 'Новый лид')}", "uoi:push_newlead_minutes"),
           (f"🔁 {r.L('Takror', 'Повтор')}", "uoi:push_repeat_minutes"), (f"🔥 {r.L('Belgilar', 'Иконки')}", "uoi:push_emojis"),
           (f"🚫 {r.L('Chiqarilgan', 'Исключены')}", "uoi:skip_emojis"),
           (f"🔍 {r.L('Bazani tekshirish', 'Проверить базу')}", "uob"),
           (f"👥 {r.L('Guruhda panel', 'Панель в группе')}", "uo:grp")]
    return ui.join(title("⚙️", r.L("PUSH SOZLAMALARI", "НАСТРОЙКИ ПУША")), "", card(lines)), kb(*grid(btn), nav(r, "u"))


def base_state(ctx, r: Req) -> str:
    """Baza to'liq tekshirilganmi: « · ✅ to'liq (412)» / « · ⏳ tekshirilmoqda…»."""
    db, ub = ctx.db, ctx.userbot
    if ub is not None and getattr(ub, "deep_running", False):
        return r.L(" · ⏳ tekshirilmoqda…", " · ⏳ проверяется…")
    if db.get("deep_scan_base") == (db.get("push_base_from") or "2026-08-28"):
        return r.L(f" · ✅ to'liq ({db.get('deep_scan_n') or 0})", f" · ✅ полная ({db.get('deep_scan_n') or 0})")
    return r.L(" · ⏳ to'liq tekshiruv kutilmoqda", " · ⏳ ждёт полной проверки")


@screen("uob", "full")
async def base_rescan(ctx, r: Req):
    """🔍 Bazani qayta to'liq tekshirish (fonda; tugagach xabar keladi)."""
    ub = ctx.userbot
    if ub is None or ub.state != "online":
        return r.L("⚠️ Asosiy akkaunt ulanmagan", "⚠️ Основной аккаунт не подключён")
    if not ub.deep_running:
        ui.bg(ub.deep_scan(force=True))
    await ui.toast(ctx.bot, r.chat_id, r.L("🔍 Tekshirilmoqda — tugagach xabar keladi",
                                           "🔍 Проверяю — по окончании пришлю сообщение"), 6)
    r.args = []
    return await settings(ctx, r)


def period_text(ctx, r: Req) -> str:
    db = ctx.db
    a, b = db.get("push_range_from"), db.get("push_range_to")
    if a or b:
        return f"{dstr(a) if a else '…'} – {dstr(b) if b else r.L('bugun', 'сегодня')}"
    days = db.get_int("push_days")
    return r.L(f"oxirgi {days} kun", f"последние {days} дн.") if days > 0 else r.L("hammasi (bazadan)", "все (с базы)")


@screen("upd", "full")
async def period_screen(ctx, r: Req):
    db = ctx.db
    if r.args:
        v = r.args[0]
        db.set("push_range_from", "")
        db.set("push_range_to", "")
        db.set("push_days", "0" if v == "all" else v)
        ui.view(r, "upd")
    cur = db.get_int("push_days") if not (db.get("push_range_from") or db.get("push_range_to")) else -1
    opts = [("7", r.L("7 kun", "7 дней")), ("14", r.L("14 kun", "14 дней")), ("30", r.L("30 kun", "30 дней")),
            ("60", r.L("60 kun", "60 дней")), ("all", r.L("Hammasi", "Все"))]
    btn = [(("✅ " if (k == "all" and cur == 0) or (k.isdigit() and int(k) == cur) else "") + t, f"upd:{k}")
           for k, t in opts]
    lines = [r.L("Lidlar haftalar o'tib eskiradi. Push faqat shu davrda o'zi yozgan lidlarga ketadi.",
                 "Лиды со временем остывают. Пуш — только тем, кто сам писал в этот период."),
             f"{r.L('Hozir', 'Сейчас')}: <b>{period_text(ctx, r)}</b>"]
    rows = grid(btn, 3) + [[(r.L("📆 Sana oralig'i", "📆 Даты"), "uoi:range")], nav(r, "uo")]
    return ui.join(title("🗓", r.L("PUSH DAVRI", "ПЕРИОД ПУША")), "", card(lines)), kb(*rows)


PROMPTS = {
    "push_limit": ("Har papkaga bir martada nechta? <code>0</code> — hammasi.", "Сколько за раз на папку? <code>0</code> — все."),
    "push_idle_minutes": ("Kunduzgi push: necha daqiqadan beri yozishmasa «jim turgan» hisoblanadi? (<code>30</code>, "
                          "<code>60</code>). Hozirgina yozishganlar oxirida bo'ladi.",
                          "Дневной push: сколько минут без переписки считать «молчит»? (<code>30</code>, <code>60</code>). "
                          "Только что писавшие — в конце."),
    "range": ("Sana oralig'i: <code>01.10.2026 20.10.2026</code> yoki bitta sana (o'sha kundan bugungacha).",
              "Даты: <code>01.10.2026 20.10.2026</code> или одна дата (с неё по сегодня)."),
    "push_base_from": ("Baza: qaysi sanadan keyin o'zi yozgan lidlar (yangi ham, eski ham)? "
                       "Masalan <code>28.08.2026</code>.",
                       "База: с какой даты лиды, писавшие сами (новые и старые)? Например <code>28.08.2026</code>."),
    "push_newlead_minutes": ("Yangi lidga necha daqiqa Push yubormaslik? (<code>60</code>, <code>2 soat</code>)",
                             "Сколько минут не слать новым лидам? (<code>60</code>, <code>2ч</code>)"),
    "push_repeat_minutes": ("Push olganlarga necha daqiqa qayta yubormaslik? (kamida 180)",
                            "Сколько минут не слать повторно? (минимум 180)"),
    "push_emojis": ("Faqat shu belgili lidlarga (masalan <code>🔥</code>). <code>*</code> — hammasiga.",
                    "Только лидам с иконкой (например <code>🔥</code>). <code>*</code> — всем."),
    "skip_emojis": ("Chiqarilgan belgilar (zaderjka va Push'da hisobga olinmaydi), masalan <code>⚡ 💊</code>.",
                    "Исключённые иконки (не учитываются в задержках и Пуше), например <code>⚡ 💊</code>."),
}


@screen("uoi", "full")
async def setting_ask(ctx, r: Req):
    key = r.args[0]
    if key not in PROMPTS:
        r.args = []
        return await settings(ctx, r)
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
    elif key == "range":
        found = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}", text)
        try:
            a = parse_date(found[0]) if found else None
            b = parse_date(found[1]) if len(found) > 1 else None
        except ValueError:
            a = None
        if a is None or (b is not None and b < a):
            return r.L("⚠️ Masalan: 01.10.2026 20.10.2026", "⚠️ Например: 01.10.2026 20.10.2026")
        db.set("push_range_from", a.isoformat())
        db.set("push_range_to", b.isoformat() if b else "")
        db.set("push_days", "0")
    elif key == "push_base_from":
        found = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}", text)
        try:
            d = parse_date(found[0]) if found else None
        except ValueError:
            d = None
        if d is None:
            return r.L("⚠️ Masalan: 28.08.2026", "⚠️ Например: 28.08.2026")
        db.set("push_base_from", d.isoformat())
        ub = ctx.userbot
        if ub is not None and ub.state == "online" and not ub.deep_running:
            ui.bg(ub.deep_scan())                      # yangi sana — baza qaytadan to'liq yig'iladi
    elif key in ("push_newlead_minutes", "push_idle_minutes", "push_repeat_minutes"):
        try:
            v = parse_minutes(text)
        except ValueError:
            return r.L("⚠️ Masalan: 60 yoki 2 soat", "⚠️ Например: 60 или 2ч")
        if key == "push_repeat_minutes":
            v = max(180, v)
        db.set(key, str(v))
    elif key in ("push_emojis", "skip_emojis"):
        db.set(key, "" if text in ("*", "0", "-") else " ".join(ch for ch in text if not ch.isspace() and ch != ","))
    r.args = []
    return await settings(ctx, r)


# ───────────────────────── jurnal
STATUS_ICON = {"done": "✅", "stopped": "⏹", "aborted": "⛔", "interrupted": "⚠️", "running": "⏳"}


def kind_label(r: Req, kind: str) -> str:
    if not kind:
        return ""
    if kind == "text":
        return r.L("📝 matn", "📝 текст")
    return (KIND_RU if r.lang == "ru" else KIND_UZ).get(kind, kind)


@screen("uh", "full")
async def history(ctx, r: Req):
    """🧾 Har Push raqami: necha marta, nechta lidga ketdi, nechtasi keyin yozdi, nechtasiga karta ketdi;
    🧪 nazorat guruhi bo'lsa — olmaganlar o'zi yozdimi (Push'ning haqiqiy ta'siri). Mazmun o'qilmaydi."""
    from . import insights as I
    db, now = ctx.db, int(ctx.clock())
    on = db.flag("an_push")
    win = db.get_int("push_reply_min", 90)
    still = r.L(" — hali sanalmoqda", " — ещё считается")
    blocks, btn = [], []
    for x in I.push_by_number(db, now, limit=10):
        p = L.get(db, x["push_id"]) if x["push_id"] else None
        head = (f"<b>📚 {h(L.label(p, r.lang, ctx.tz))}</b>" if p is not None else
                f"<b>📣 {r.L('Raqamsiz (eski)', 'Без номера (старые)')}</b>")
        times = ", ".join(SLOT_ICON.get(s, "") + fmt(t, ctx.tz) for t, s in list(zip(x["times"], x["slots"]))[:4]) \
            + (" …" if len(x["times"]) > 4 else "")
        lines = [head, r.L(f"Yuborildi: <b>{x['n']}</b> ta lidga · {len(x['times'])} marta ({times})",
                           f"Отправлено: <b>{x['n']}</b> лидам · {len(x['times'])} раз ({times})")]
        if on and x["n"]:
            lines.append(r.L(f"Javob yozdi: <b>{x['rep']}</b> ({I.pct(x['rep'], x['n'])})",
                             f"Ответили: <b>{x['rep']}</b> ({I.pct(x['rep'], x['n'])})") + (still if x["rep_open"] else "")
                         + " · " + r.L(f"karta: <b>{x['card']}</b> ({I.pct(x['card'], x['n'])})",
                                       f"карта: <b>{x['card']}</b> ({I.pct(x['card'], x['n'])})")
                         + (still if x["card_open"] and not x["rep_open"] else ""))
        if on and x["hn"]:
            d_rep = (x["rep"] / x["n"] if x["n"] else 0) - (x["hrep"] / x["hn"])
            d_card = (x["card"] / x["n"] if x["n"] else 0) - (x["hcard"] / x["hn"])
            few = r.L(" · kam — taxminiy", " · мало — примерно") if x["hn"] < 20 else ""
            lines.append(r.L(f"🧪 Olmaganlar ({x['hn']} ta): o'zi yozdi {I.pct(x['hrep'], x['hn'])}, karta "
                             f"{I.pct(x['hcard'], x['hn'])} → Push ta'siri: javob {d_rep * 100:+.0f}%, karta "
                             f"{d_card * 100:+.0f}%{few}",
                             f"🧪 Не получили ({x['hn']}): написали сами {I.pct(x['hrep'], x['hn'])}, карта "
                             f"{I.pct(x['hcard'], x['hn'])} → эффект Пуша: ответы {d_rep * 100:+.0f}%, карта "
                             f"{d_card * 100:+.0f}%{few}"))
        blocks.append("\n".join(lines))
        if on and x["n"] and x["push_id"]:
            btn.append([(f"📁 №{x['push_id']} — {r.L('RD bo‘yicha', 'по RD')}", f"uhb:{x['push_id']}")])
    parts = [title("🧾", r.L("PUSH NATIJASI", "РЕЗУЛЬТАТ ПУША"), r.L("har Push raqami bo'yicha", "по номерам Пуша")), "",
             card(["\n\n".join(blocks)]) if blocks else r.L("<i>Hozircha bo'sh.</i>", "<i>Пока пусто.</i>")]
    if on:
        parts.append(r.L(f"<i>Javob yozdi — Push'dan keyin {win} daqiqa ichida yozgan lidlar. Karta — 24 soat ichida "
                         "xodim karta yuborgan lidlar (/rek /dep /cash). «hali sanalmoqda» — vaqt tugamagan.</i>",
                         f"<i>Ответили — написавшие в течение {win} мин после Пуша. Карта — кому за 24 ч сотрудник "
                         "отправил карту (/rek /dep /cash). «ещё считается» — время не вышло.</i>"))
    return ui.join(*parts), kb(*btn[:8], nav(r, "u"))


@screen("uhb", "full")
async def history_folders(ctx, r: Req):
    """Bitta Push raqami — RD bo'yicha."""
    from . import insights as I
    pid = int(r.args[0])
    p = must(L.get(ctx.db, pid))
    names = {f["id"]: f["name"] for f in P.folders(ctx.db)}
    lines = ["\n".join([f"<b>📁 {h(names.get(fid, '?'))}</b>",
                        r.L(f"Yuborildi: {n} · javob yozdi: {rep} ({I.pct(rep, n)}) · karta so'radi: {crd} ({I.pct(crd, n)})",
                            f"Отправлено: {n} · ответили: {rep} ({I.pct(rep, n)}) · карту попросили: {crd} "
                            f"({I.pct(crd, n)})")])
             for fid, n, rep, crd in I.push_by_folder(ctx.db, pid)]
    sub = L.label(p, r.lang, ctx.tz)
    return ui.join(title("🧾", r.L("PUSH NATIJASI", "РЕЗУЛЬТАТ ПУША"), sub), "",
                   card(lines or [r.L("Ma'lumot yo'q", "Нет данных")])), kb(nav(r, "uh"))
