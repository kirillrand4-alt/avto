# -*- coding: utf-8 -*-
"""Что дала передача адресов работнику: кого он вскрыл и что сняли."""
import io
import json
import os
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("== письма, снятые пробой (по решению «проба адресов») ==")
for r in c.execute(
        "SELECT substr(decided_at,1,10) d, COUNT(*) n FROM confirm_reviews "
        "WHERE decided_by='проба адресов' GROUP BY d ORDER BY d DESC LIMIT 5"):
    print(f"  {r['d']}  {r['n']}")

print("\n== свежие вердикты работника (по его файлу, ts сегодня) ==")
Ф = r"C:\sender\_ops\probe-rezultat.jsonl"
сег = Counter()
if os.path.exists(Ф):
    for s in io.open(Ф, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
        except Exception:                                        # noqa: BLE001
            continue
        if str(z.get("ts") or "")[:10] == "2026-08-20":
            сег[str(z.get("verdict") or "")] += 1
for k, n in сег.most_common():
    print(f"  {n:>5}  {k}")
print("  (файл на сервере может отставать — он скачивался раньше)")

print("\n== очередь сейчас ==")
for r in c.execute(
        "SELECT COALESCE(p.source,'(старая проба)') ист, "
        "       COALESCE(p.verdict,'нет') v, COUNT(*) n "
        "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
        "LEFT JOIN addr_probe p ON p.email=lower(cr.email) "
        "WHERE cr.status IN ('approved','edited') "
        "AND m.status IN ('scheduled','sending') "
        "GROUP BY ист, v ORDER BY n DESC"):
    print(f"  {r['n']:>4}  {r['v']:<16} {r['ист']}")

print("\n== отправлено и отбилось сегодня ==")
о = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' "
              "AND substr(updated_at,1,10)=date('now')").fetchone()[0]
б = c.execute("SELECT COUNT(*) FROM events WHERE event_type='bounce' "
              "AND substr(created_at,1,10)=date('now')").fetchone()[0]
print(f"  отправлено {о} | отбилось {б} "
      f"({100.0 * б / о if о else 0:.1f}%)")
