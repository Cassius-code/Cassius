"""Bosh ekranlar uchun rasm-kartochka bloklari (cards.render chizadi). Matn ham saqlanadi: rasm o'chiq bo'lsa
yoki chizib bo'lmasa — oddiy matn ko'rinadi.

Pul ko'rinishi matndagi bilan bir xil qoidada: kartochkaga faqat shu odam matnda ko'radigan raqamlar tushadi."""
from __future__ import annotations

import datetime as dt

WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr",
             "dekabr"]
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
             "ноября", "декабря"]


def when(r, t: dt.datetime | dt.date, clock: bool = True) -> str:
    ru = r.lang == "ru"
    wd = (WEEKDAYS_RU if ru else WEEKDAYS_UZ)[t.weekday()]
    s = f"{wd}, {t.day} {(MONTHS_RU if ru else MONTHS_UZ)[t.month - 1]}"
    return s + (f" · {t:%H:%M}" if clock and isinstance(t, dt.datetime) else "")


def delta(cur: float, prev: float | None) -> str:
    """«↑12%» / «↓5%» — kartochkada strelka bilan chiziladi."""
    if prev is None or prev <= 0:
        return ""
    d = round((cur - prev) / prev * 100)
    return "" if d == 0 else f"{'↑' if d > 0 else '↓'}{abs(d)}%"


def onoff(r, v: bool) -> str:
    return r.L("yoqilgan", "включено") if v else r.L("o'chiq", "выключено")


# ───────────────────────── bosh menyu
def main(r, t: dt.datetime, alive: bool, waiting: int, delays: int, stavka: int, came: int, staff: int,
         cash: str | None, cash_ready: bool, ub_ok: bool, push_on: int, push_all: int, group_ok: bool) -> list:
    blocks = [("head", "RD Control", when(r, t), alive, "ONLINE" if alive else "STOP"),
              ("tiles", [(r.L("Javob kutyapti", "Ждут ответа"), str(waiting), "", None, "⏱", None),
                         (r.L("Zaderjka", "Задержки"), str(delays), "", "bad" if delays else None, "🚨", None),
                         (r.L("Stavkada", "В ставке"), str(stavka), "", None, "🎬", None),
                         (r.L("Ishda", "На работе"), str(came), f"/ {staff}", "good" if staff and came >= staff
                          else None, "🙋", (came / staff) if staff else None)])]
    if cash is not None:
        blocks.append(("wide", "Cash", r.L("shu hafta · Du–Ya", "эта неделя · Пн–Вс") if cash_ready else
                       r.L("≈ hafta hali hisoblanmagan", "≈ неделя ещё не рассчитана"),
                       ("" if cash_ready else "≈ ") + f"{cash} $", "💰"))
    blocks.append(("chips", [(r.L("Akkaunt", "Аккаунт"), ub_ok),
                             (f"Push {push_on}/{push_all}", not push_all or push_on == push_all),
                             ("«Проёб»", group_ok)]))
    return blocks


# ───────────────────────── nazorat
def control(r, enabled: bool, waiting: int, delays: int, stavka: int, limit: str, hours: str, stavka_on: bool,
            need: int, fine: str) -> list:
    return [("head", r.L("Nazorat", "Контроль"), r.L("zaderjka · stavka · jarima", "задержки · ставка · штрафы"),
             enabled, r.L("YOQILGAN", "ВКЛ") if enabled else r.L("O'CHIQ", "ВЫКЛ")),
            ("tiles", [(r.L("Hozir kutyapti", "Сейчас ждут"), str(waiting), "", None, "⏳", None),
                       (r.L("Zaderjka bugun", "Задержки сегодня"), str(delays), "", "bad" if delays else None, "🚨",
                        None),
                       (r.L("Stavkada", "В ставке"), str(stavka), "", None, "🎬", None),
                       (r.L("Limit", "Лимит"), limit, r.L("daq", "мин"), None, "⏱", None)]),
            ("rows", r.L("Qoidalar", "Правила"),
             [(r.L("Ish vaqti", "Рабочее время"), hours, "🕒"),
              (r.L("Stavka", "Ставка"), (f"{need} " + r.L("video", "кружка")) if stavka_on else onoff(r, False), "🎬"),
              (r.L("Avto-jarima", "Авто-штраф"), fine, "💸")])]


# ───────────────────────── kassa
def kassa(r, t: dt.date, day_raw: int, day_n: int, week_raw: int, week_delta: str, cash: str | None,
          cash_ready: bool, income: str | None, top: list, notes: list) -> list:
    from .kassa_view import num
    blocks = [("head", r.L("Kassa", "Касса"), when(r, t, clock=False), None, ""),
              ("tiles", [(r.L("Bugun", "Сегодня"), num(day_raw), r.L(f"{day_n} chek", f"{day_n} чек."), None, "📅",
                          None),
                         (r.L("Shu hafta", "Эта неделя"), num(week_raw), week_delta, None, "🗓", None)])]
    if cash is not None:
        blocks.append(("wide", "Cash", r.L("xodimlar oyligi · shu hafta", "зарплаты сотрудников · неделя") if cash_ready
                       else r.L("≈ hafta hali hisoblanmagan", "≈ неделя ещё не рассчитана"),
                       ("" if cash_ready else "≈ ") + f"{cash} $", "💰"))
    if top:
        blocks.append(("rows", r.L("Reyting · top 3", "Рейтинг · топ 3"),
                       [(n, num(v), str(i + 1)) for i, (n, v, _p) in enumerate(top[:3])]))
    rows = list(notes)
    if income is not None:
        rows.insert(0, (r.L("Daromadingiz (hafta)", "Ваш доход (неделя)"), f"{income} $", "💼"))
    if rows:
        blocks.append(("rows", r.L("Diqqat", "Внимание") if notes else r.L("Siz", "Вы"), rows))
    return blocks


# ───────────────────────── push
def push(r, slot: str, slot_name: str, online: int, accs: int, groups: list, total: int | None, cooled: int,
         minutes: int, folders: list, running: str | None) -> list:
    blocks = [("head", "Push", slot_name, (not accs) or online == accs, f"{online} / {accs}")]
    if groups:
        blocks.append(("tiles", groups))
    if running is not None:
        blocks.append(("wide", r.L("Yuborilmoqda", "Идёт рассылка"), "", running, "🚀"))
    elif total is not None:
        sub = (r.L(f"hozir gaplashayotgan {cooled} ta — tegilmaydi", f"в переписке {cooled} — не трогаем")
               if cooled else r.L(f"≈ {minutes} daqiqa", f"≈ {minutes} мин"))
        blocks.append(("wide", r.L("Yuboriladi", "К отправке"), sub, str(total), "🚀"))
    if folders:
        blocks.append(("rows", r.L("Papkalar", "Папки"), folders[:6]))
    return blocks


# ───────────────────────── xodimlar
def people(r, active: int, came: int, staff: int, folders: int, archived: int, today_rows: list) -> list:
    blocks = [("head", r.L("Xodimlar", "Сотрудники"), r.L("jamoa va ishga kelish", "команда и приход"), None, ""),
              ("tiles", [(r.L("Xodimlar", "Сотрудники"), str(active), "", None, "🙋", None),
                         (r.L("Ishda", "На работе"), str(came), f"/ {staff}", None, "🕒",
                          (came / staff) if staff else None),
                         (r.L("Papkalar", "Папки"), str(folders), "", None, "📁", None),
                         (r.L("Arxivda", "В архиве"), str(archived), "", None, "🗓", None)])]
    if today_rows:
        blocks.append(("rows", r.L("Bugun", "Сегодня"), today_rows[:6]))
    return blocks


def person(r, name: str, sub: str, status: str, ok: bool | None, tiles: list, cash: str | None, cash_sub: str,
           rows: list) -> list:
    blocks = [("head", name, sub, ok, status)]
    if tiles:
        blocks.append(("tiles", tiles))
    if cash is not None:
        blocks.append(("wide", "Cash", cash_sub, f"{cash} $", "💰"))
    if rows:
        blocks.append(("rows", r.L("Ko'rsatkichlar", "Показатели"), rows))
    return blocks


# ───────────────────────── hisobotlar, sozlamalar
def reports(r, t: dt.datetime, delays_d: int, delays_w: int, came: int, staff: int, kassa_d: str | None,
            kassa_w: str | None) -> list:
    tiles = [(r.L("Zaderjka · bugun", "Задержки · сегодня"), str(delays_d), "", "bad" if delays_d else None, "🚨",
              None),
             (r.L("Zaderjka · hafta", "Задержки · неделя"), str(delays_w), "", None, "🗓", None)]
    if kassa_d is not None:
        tiles += [(r.L("Kassa · bugun", "Касса · сегодня"), kassa_d, "", None, "💵", None),
                  (r.L("Kassa · hafta", "Касса · неделя"), kassa_w, "", None, "📅", None)]
    else:
        tiles += [(r.L("Ishda", "На работе"), str(came), f"/ {staff}", None, "🙋", (came / staff) if staff else None)]
    return [("head", r.L("Hisobotlar", "Отчёты"), when(r, t), None, ""), ("tiles", tiles)]


def settings(r, alive: bool, rows: list, chips: list) -> list:
    return [("head", r.L("Sozlamalar", "Настройки"), r.L("bot holati", "состояние бота"), alive,
             "ONLINE" if alive else "STOP"),
            ("rows", r.L("Holat", "Состояние"), rows),
            ("chips", chips)]


def theme_preview(r, name: str) -> list:
    """Mavzu tanlash ekrani: namunaviy bosh menyu."""
    return [("head", "RD Control", name, True, "ONLINE"),
            ("tiles", [(r.L("Javob kutyapti", "Ждут ответа"), "3", "", None, "⏱", None),
                       (r.L("Zaderjka", "Задержки"), "1", "", "bad", "🚨", None),
                       (r.L("Stavkada", "В ставке"), "5", "", None, "🎬", None),
                       (r.L("Ishda", "На работе"), "3", "/ 3", "good", "🙋", 1.0)]),
            ("wide", "Cash", r.L("namuna", "пример"), "1 240 $", "💰")]
