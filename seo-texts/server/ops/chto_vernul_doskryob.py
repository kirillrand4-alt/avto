# -*- coding: utf-8 -*-
"""Что вернул доскрёб: карточки лидов и НАСТОЯЩАЯ дата ответа клиента."""
import json
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

С = int(sys.argv[1]) if len(sys.argv) > 1 else 512
store = Store(r"C:\sender\sender.db")
строки = []
with store._lock:
    c = store._conn
    кол = [x[1] for x in c.execute("PRAGMA table_info(leads)")]
    сн_к = next((x for x in ("snippet", "last_snippet", "reply_snippet",
                             "text", "body") if x in кол), None)
    вид_к = next((x for x in ("reply_kind", "kind") if x in кол), None)
    лиды = c.execute(
        "SELECT id, email, company_name, status, created_at%s%s "
        "  FROM leads WHERE id >= ? ORDER BY id"
        % (", " + вид_к if вид_к else "", ", " + сн_к if сн_к else ""),
        (С,)).fetchall()
    for л in лиды:
        # когда клиент реально ответил
        р = c.execute(
            "SELECT e.event_ts, e.event_type, e.mailbox_id FROM events e "
            "  JOIN recipients rc ON e.recipient_id = rc.id "
            " WHERE rc.email = ? AND e.event_type IN ('reply','reply_auto') "
            " ORDER BY e.id DESC LIMIT 1", (л["email"],)).fetchone()
        строки.append("   лид %-5s %-28s %-30s"
                      % (л["id"], str(л["email"])[:28],
                         str(л["company_name"])[:30]))
        строки.append("       ответ клиента: %-20s вид: %-14s ящик: %s"
                      % (str(р["event_ts"])[:19] if р else "не нашли",
                         str((л[вид_к] if вид_к else "-") or "-")[:14],
                         str(р["mailbox_id"])[:34] if р else "-"))
        сн = " ".join(str((л[сн_к] if сн_к else "") or "").split())[:150]
        строки.append("       %s" % сн)
print("\n".join(строки))
print("")
print("=" * 74)
print("=== КАРТОЧКИ, ВЕРНУВШИЕСЯ ПОСЛЕ ПОЧИНКИ КЛЮЧА (с id %d) ===" % С)
print("   всего карточек: %d" % len(лиды))
