"""Sozlamalar: Railway Variables (sirlar) va bazadagi o'zgaruvchan sozlamalar (panel orqali)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Panel orqali o'zgaradigan sozlamalar (boshlang'ich qiymatlar). Kalitlar bazadagi settings jadvalida.
DEFAULTS: dict[str, str] = {
    "lang": "uz",                    # panel tili: uz / ru
    "bot_enabled": "1",              # bosh yoqgich: 0 — bot hech narsa qilmaydi (panel ishlaydi)
    # ── nazorat (zaderjka)
    "delay_enabled": "1",
    "limit_minutes": "20",           # mijozga javob limiti
    "remind_on": "1",                # ⏰ javobsiz zaderjka: eslatma, keyin jarima
    "remind_min": "15",              # «задержка» chiqqanidan shuncha daqiqa o'tib ham javob yo'q — eslatma
    "remind_grace_min": "5",         # eslatmadan keyin shuncha daqiqa — javob bo'lmasa jarima
    "remind_fine_usd": "5",          # jarima ($) — o'sha kuni papkada ishlayotgan har xodimga
    "clean_delay_min": "10",         # 🧹 «задержка» xabari javobdan shuncha daqiqa keyin o'chadi (0 — o'chmaydi)
    "clean_info_min": "60",          # 🧹 boshqa avtomat xabarlar yozilganidan shuncha daqiqa keyin o'chadi (0 — o'chmaydi)
    "newlead_quiet_min": "120",      # 🆕 bugungi yangi lidga shuncha daqiqa (ish vaqtida) hech kim yozmasa — eslatma (0 — o'chiq)
    "pay_remind_min": "15",          # 💳 karta ketgach shuncha daqiqa hech kim yozmasa — xodimga eslatma (0 — o'chiq)
    "push_group": "1",               # 📣 Push ketayotganda «Проёб»da panel (hamma ko'radi), tugagach — xodimlarga xabar
    "push_panel": "",                # ketayotgan Push paneli: bid:gid:mid
    "push_panel_del": "",            # tugagan Push paneli o'chadigan vaqt: gid:mid:ts
    "board_on": "1",                 # 📌 «Проёб»da qadalgan «Задержки сейчас» (har RD, jonli)
    "board_msg_id": "",
    "board_gid": "",
    "board_text": "",
    "wait_slide_min": "5",           # mijoz birinchi xabaridan shu daqiqa ichida yana yozsa — oxirgisidan hisoblanadi
    "work_start": "10:00",           # ish boshlanishi (hamma uchun bir xil)
    "work_end": "23:00",             # ish tugashi
    "delay_from": "0",               # zaderjka shu vaqtdan keyingi xabarlar bo'yicha (o'rnatilgan payt)
    "eod_enabled": "1",              # ish tugagach (1 daqiqadan keyin) javobsiz chatlar ro'yxati «Проёб»ga
    "eod_last": "",
    "fines_enabled": "1",            # avtomat jarimalar (zaderjka va kech qolish): 0 — hech kimga yozilmaydi
    "fine_min_leads": "3",           # papkada bir vaqtda shuncha lid javobsiz bo'lsa — «holat»
    "fine_forgive": "2",             # har kuni har papkaga shuncha holat kechiriladi (faqat ogohlantirish)
    "fine_grace": "3",               # kechirimlar tugagach: ogohlantirishdan keyin shuncha daqiqada javob bo'lmasa — jarima
    "fine_amount": "0",              # zaderjka jarimasi summasi ($), hamma papkaga (papkada alohida summa bo'lmasa)
    "fine_episode": "30",            # holatdan keyin shu daqiqa ichidagi kechikishlar — o'sha holatning davomi
    "skip_emojis": "⚡ 💊",           # bunday lidlar zaderjka va Push'da hisobga olinmaydi
    "delay_batch": "1",              # yaqin zaderjkalar 40 soniya kutib, bitta xabar bo'lib ketadi
    # ── tahlil (har biri yoqiladi/o'chiriladi)
    "an_heatmap": "1",               # 🕐 soatlar: qachon lid ko'p yozadi, qachon zaderjka
    "an_stale": "1",                 # 💤 qotib qolgan lidlar
    "stale_days": "3",
    "an_cooling": "1",               # 📉 soviyotgan lidlar
    "cooling_days": "2",
    "cool_auto": "1",                # 📉 soviyotgan lidni «Проёб»da o'zi eslatadi (papka xodimini belgilab)
    "an_speed": "1",                 # ⚡ javob tezligi → karta va 🏆 g'oliblar formulasi
    "an_push": "1",                  # 📣 Push natijasi (90 daqiqada yozdi, 24 soatda karta)
    "push_reply_min": "90",
    "an_cards": "1",                 # 💳 kartalar: har RD da qaysi lidga necha marta
    "spam_check": "1",               # 🛡 har kuni Push akkauntlarni @SpamBot da tekshirish
    "spam_check_last": "",
    "cards_since": "",               # karta va Push natijasi shu vaqtdan yig'iladi
    "card_cmds": "/rek /dep /cash",  # xodim topikda shu buyruqni yozsa — lidga karta ketdi (hamma RD; CRM o'zgartirsa — panelda)
    "proyob_group_id": "",
    "proyob_sender": "bot",          # «Проёб»ga kim yozadi: bot | main (asosiy akkaunt; anonim admin — guruh nomidan)
    # ── stavka (yangi lid)
    "stavka_enabled": "1",
    "stavka_count": "3",             # nechta dumaloq video stavkani tugatadi
    "stavka_first": "20",            # yangi chatdan keyin shu daqiqada birinchi stavka kelmasa — «ставка» eslatmasi
    "stavka_next": "20",             # keyingi stavka oldingisidan (yoki eslatmadan) shu daqiqada kelmasa — yana eslatma
    "stavka_max_remind": "3",        # bitta lidga ko'pi bilan nechta eslatma; oxirgisidan keyin stavka tugaydi
    "echo_seconds": "0",             # >0: xodim xabaridan keyin shu soniya ichidagi bot xabari hisoblanmaydi (egasi: kerak emas)
    "bet_text_seconds": "20",        # videodan keyin shu soniya ichidagi bot matni = stavkaning o'zi (jurnalda 0–1 s)
    # ── ishga kelish va tanaffus
    "attendance_enabled": "1",
    "noshow_minutes": "15",          # ish boshlanib N daqiqa o'tib «доброе утро» yo'q bo'lsa — eslatma
    "late_fine": "",                 # kech qolish: «0.5» — har daqiqaga $, «10=2, 30=5» — 10+ daq → 2$, 30+ daq → 5$
    "late_free_min": "0",            # kech qolish: shuncha daqiqagacha jarima yo'q (bepul daqiqalar)
    "late_count": "over",            # over — faqat bepuldan ortiq daqiqalar × narx; all — hamma kech daqiqalar × narx
    "breaks_enabled": "1",
    "break_minutes": "30",
    "breaks_per_day": "3",
    # ── Push
    "push_enabled": "1",
    "push_text": "",
    "push_media": "",
    "push_limit": "50",              # HAR papkaga nechta
    "push_speed": "normal",
    "push_emojis": "",               # bo'sh = hammasi (chiqarilganlardan tashqari)
    "push_from": "",
    "push_to": "",
    "push_newlead_minutes": "60",
    "push_idle_minutes": "60",       # kunduzgi push: shuncha daqiqa yozishmagan — «jim turgan»
    "push_base_from": "2026-08-28",  # baza: shu sanadan beri o'zi yozgan lidlar
    "push_days": "0",                # davr: oxirgi N kun (0 — bazadan beri hammasi)
    "push_range_from": "",           # yoki aniq sana oralig'i
    "push_range_to": "",
    "push_morning_until": "13:00",   # 🌅 ertalabki push shu vaqtgacha
    "push_evening_from": "19:00",    # 🌙 kechki push shu vaqtdan
    "push_repeat_minutes": "180",
    "push_quiet_from": "",
    "push_quiet_to": "",
    "push_auto": "0",                # jadval bo'yicha avtomat Push
    "push_times": "10:30,15:00,20:00",
    "push_auto_last": "",            # oxirgi avtomat Push (sana+vaqt kaliti)
    # ── kassa
    "zp_mode": "button",             # button — hafta «🧮 Haftani hisoblash» bilan; auto — doim; off — o'zingiz hisoblaysiz
    "kassa_notify": "1",             # har hisobotdan keyin egaga xodimning shu kungi xulosasi (eski kassa botidagidek)
    # ── hisobotlar
    "report_enabled": "0",           # egasi: hisobot faqat buyruq bilan (/hisobot), avtomat yuborilmaydi
    "report_time": "23:30",
    "report_last": "",
    "weekly_enabled": "0",           # egasi: haftalik xulosa faqat /statistika bilan
    "weekly_last": "",
    "backup_last": "0",
    # ── tizim
    "userbot_session": "",
    "track_from": "",                # lidlar hisobi shu sanadan (bo'sh = o'rnatilgan kun)
    "kassa_imported": "",
    "old_imported": "",
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    owner_ids: tuple[int, ...]       # to'liq huquqli egalar (Railway: ADMIN_IDS yoki OWNER_ID)
    api_id: int
    api_hash: str
    data_dir: Path
    tz_name: str
    log_level: str
    old_db: Path                     # eski zaderjka botining bazasi (bir marta ko'chiriladi)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "rdbot.sqlite3"

    @property
    def main_owner(self) -> int:
        return self.owner_ids[0]


def _ids(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            v = int(part)
            if v not in out:
                out.append(v)
    return tuple(out)


def load_config(env: dict | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    token = (env.get("BOT_TOKEN") or "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN berilmagan (Railway → Variables)")
    owners = _ids(env.get("OWNER_ID", "")) + tuple(i for i in _ids(env.get("ADMIN_IDS", ""))
                                                   if i not in _ids(env.get("OWNER_ID", "")))
    if not owners:
        raise ConfigError("ADMIN_IDS (yoki OWNER_ID) berilmagan — sizning Telegram ID raqamingiz")
    api_raw = (env.get("API_ID") or "0").strip()
    try:
        api_id = int(api_raw or 0)
    except ValueError as exc:
        raise ConfigError("API_ID son bo'lishi kerak (my.telegram.org)") from exc
    data_dir = Path(env.get("DATA_DIR") or "./data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        bot_token=token,
        owner_ids=owners,
        api_id=api_id,
        api_hash=(env.get("API_HASH") or "").strip(),
        data_dir=data_dir,
        tz_name=(env.get("TZ_NAME") or "Asia/Tashkent").strip(),
        log_level=(env.get("LOG_LEVEL") or "INFO").upper(),
        old_db=Path(env.get("OLD_DB") or str(data_dir / "tgcontrol.sqlite3")),
    )
