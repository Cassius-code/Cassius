"""«Проёб» guruhi uchun xabar ko'rinishi (ruscha, HTML): qalin sarlavha → raqamlangan lidlar kartasi → kim.

Hamma matn shu yerdan o'tadi: ismlar, papka nomlari, lid nomlari HTML uchun xavfsiz (escape) qilinadi."""
from __future__ import annotations

import html

from . import people as P


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def lead_line(i: int, url: str, label: str, note: str = "", done: bool = False) -> str:
    """«1. <lid nomi — havola> · ждёт с 14:05»; yopilgani — ✅ bilan."""
    name = esc((label or "").strip() or "чат")
    link = f'<a href="{html.escape(url, quote=True)}">{name}</a>'
    return f"{'✅ ' if done else ''}{i}. {link}" + (f" · {esc(note)}" if note else "")


def card_lines(lines: list[str]) -> str:
    lines = [x for x in lines if x]
    return "<blockquote>" + "\n".join(lines) + "</blockquote>" if lines else ""


def mentions(people) -> str:
    return " ".join(esc(P.mention(p)) for p in people)


def who_line(people, action: str) -> str:
    """«👤 @ivan @aziza — ответьте клиентам». Xodim biriktirilmagan bo'lsa — eslatma."""
    m = mentions(people)
    return f"👤 {m} — {esc(action)}" if m else f"👤 <i>сотрудник папки не назначен</i> — {esc(action)}"
