# -*- coding: utf-8 -*-
"""Что написали клиенты в карточках, закрытых «не интересно».

Печатаем слова клиента без цитаты нашего же письма: почтовики подшивают
исходник к ответу, и в поле лида он занимает девять десятых текста.
"""
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

# Где кончается ответ и начинается подшитый исходник.
_ГРАНИЦЫ = [
    re.compile(r"^\s*-{6,}\s*$"),
    re.compile(r"^\s*-{2,}\s*Пересылаемое сообщение\s*-{2,}", re.I),
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}", re.I),
    re.compile(r"^\s*(Кому|От кого|Отправлено|From|To|Sent)\s*:", re.I),
    re.compile(r"^\s*\d{1,2}\.\d{2}\.\d{4},?\s+\d{1,2}:\d{2}.*:\s*$"),
    re.compile(r"^\s*>"),
    re.compile(r"^\s*В\s+\w+,\s+\d.*(написал|wrote)", re.I),
]


def bez_citaty(текст: str) -> str:
    """Ответ клиента без подшитого исходника. Пусто не отдаём."""
    строки = str(текст or "").splitlines()
    свои = []
    for с in строки:
        if any(г.search(с) for г in _ГРАНИЦЫ):
            break
        свои.append(с)
    итог = "\n".join(свои).strip()
    return итог or str(текст or "").strip()


store = Store(r"C:\sender\sender.db")
блоки = []
with store._lock:
    c = store._conn
    лиды = c.execute(
        "SELECT id, company_name, email, inn, status, reply_kind, recipient_id "
        "  FROM leads WHERE status='not_interested' AND reply_kind='interested'"
        " ORDER BY id DESC").fetchall()
    for л in лиды:
        куски = ["", "=" * 74,
                 "ЛИД %s — %s   (%s)" % (л["id"], л["company_name"], л["email"])]
        # когда закрыл
        з = c.execute(
            "SELECT created_at FROM lead_events WHERE lead_id=? "
            "  AND to_status='not_interested' ORDER BY id DESC LIMIT 1",
            (л["id"],)).fetchone()
        куски.append("закрыт %s" % (str(з["created_at"])[:16] if з else "?"))
        # все ответы этой компании
        n = 0
        for р in c.execute(
                "SELECT e.event_ts, e.detail_json FROM events e "
                "  JOIN recipients rc ON e.recipient_id = rc.id "
                " WHERE rc.inn = ? AND e.event_type IN ('reply','reply_auto') "
                " ORDER BY e.id", (л["inn"],)):
            import json
            try:
                д = json.loads(р["detail_json"] or "{}")
            except Exception:                                   # noqa: BLE001
                д = {}
            текст = bez_citaty(д.get("snippet") or "")
            n += 1
            куски.append("")
            куски.append("  ответ %d — %s:" % (n, str(р["event_ts"])[:16]))
            for с in текст.splitlines()[:14]:
                куски.append("     " + с[:150])
        if not n:
            куски.append("  ответов в журнале не нашлось")
        блоки.append("\n".join(куски))

print("\n".join(блоки))
print("")
print("=" * 74)
print("=== ОТВЕТЫ ИЗ ЗАКРЫТЫХ КАРТОЧЕК: %d штук ===" % len(лиды))
