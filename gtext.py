"""«Проёб» guruhi uchun xabar ko'rinishi (ruscha, HTML) — oddiy va ixcham:

    Rd 2 · задержка · ждёт с 14:49        ← mayda (kursiv)
    https://t.me/c/…/5040                  ← havolalar — oddiy
    @vealorian                             ← mayda

Ismlar, papka nomlari HTML uchun xavfsiz (escape) qilinadi."""
from __future__ import annotations

import html

from . import people as P


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def small(s: str) -> str:
    """Ikkinchi darajali qator (Telegram'da shrift o'lchami yo'q — ingichka kursiv). s — tayyor (escape qilingan)."""
    return f"<i>{s}</i>" if s else ""


def head(folder: str, *parts: str) -> str:
    """«Rd 2 · задержка · ждёт с 14:49» — mayda."""
    return small(" · ".join(x for x in (esc(folder),) + tuple(esc(p) for p in parts) if x))


def link(url: str, done: bool = False) -> str:
    """Havolaning o'zi (oddiy); javob berilgani — ✅ bilan."""
    return ("✅ " if done else "") + esc(url)


def card_lines(lines: list[str]) -> str:
    lines = [x for x in lines if x]
    return "<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else ""


def mentions(people) -> str:
    return " ".join(esc(P.mention(p)) for p in people)


def usd(v) -> str:
    """5 → «5», 2.5 → «2.5», 6.15 → «6.15»."""
    v = round(float(v or 0), 2)
    return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:g}"


def fine_line(people, amount, reason: str = "") -> str:
    """Jarima yozildi — qisqa va muloyim: «💸 @baxa, вам штраф 5 $ за задержку»."""
    who = ", ".join(esc(P.mention(p)) for p in people) or "сотрудник"
    return f"💸 {who}, вам штраф {usd(amount)} $" + (f" {esc(reason)}" if reason else "")


def tag(people, note: str = "") -> str:
    """«@ivan @aziza — note» — mayda. Xodim biriktirilmagan bo'lsa — eslatma."""
    m = mentions(people) or "сотрудник папки не назначен"
    return small(m + (f" — {esc(note)}" if note else ""))
