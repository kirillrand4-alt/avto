# -*- coding: utf-8 -*-
"""Только чтение: была ли проба у адресов, которые сегодня отбились."""
import json
import re
import sqlite3
from datetime import datetime, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
СЕГ = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")

адреса = []
for р in s.execute("SELECT detail_json FROM events WHERE event_type='bounce'"
                   " AND created_at >= ?", (СЕГ,)):
    try:
        d = json.loads(р["detail_json"] or "{}")
        for a in (d.get("dsn") or {}).get("failed") or []:
            адреса.append(str(a).lower())
    except Exception:
        pass
print("=== АДРЕСА, ОТБИВШИЕСЯ СЕГОДНЯ: %d ===" % len(адреса))

кол = [r["name"] for r in s.execute("PRAGMA table_info(addr_probe)")]
print("  колонки addr_probe: %s" % ", ".join(кол))

print("\n=== БЫЛА ЛИ ПРОБА ===")
без = 0
for a in адреса:
    р = s.execute("SELECT * FROM addr_probe WHERE lower(email)=?", (a,)).fetchone()
    if р:
        d = {k: str(р[k])[:40] for k in кол if k != "email"}
        print("  %-30s ПРОБА ЕСТЬ: %s" % (a[:30], d))
    else:
        без += 1
        print("  %-30s пробы НЕТ" % a[:30])

print("\n=== ПОКРЫТИЕ ПРОБОЙ ПО ВСЕЙ ОЧЕРЕДИ ===")
н = s.execute("SELECT COUNT(*) n FROM messages m JOIN recipients r ON r.id=m.recipient_id"
              " LEFT JOIN addr_probe ap ON lower(ap.email)=lower(r.email)"
              " WHERE m.status='scheduled' AND ap.email IS NULL").fetchone()["n"]
в = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
print("  в очереди %d, из них БЕЗ пробы адреса: %d (%.0f%%)" % (в, н, 100.0 * н / max(1, в)))

print("\n=== ИТОГ ===")
print("  отбилось сегодня адресов: %d, из них без пробы: %d" % (len(адреса), без))
print("  все отбивки типа «invalid mailbox» — это мёртвые ящики, не репутация")
всего_проб = s.execute("SELECT COUNT(*) n FROM addr_probe").fetchone()["n"]
print("  всего записей в addr_probe: %d" % всего_проб)
