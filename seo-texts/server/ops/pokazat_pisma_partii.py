# -*- coding: utf-8 -*-
"""Показать письма партии вторых адресов целиком: pokazat_pisma_partii.py N [шаг]."""
import io
import json
import sqlite3
import sys

СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 4
СДВИГ = int(sys.argv[2]) if len(sys.argv) > 2 else 0
партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = (str(d["inn"]), d["email"].lower())
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партия))
строки = c.execute(
    "SELECT cr.id, cr.email, cr.subject, cr.body, cr.inn, cr.panel_json, "
    "       r.company_name, r.contact_name "
    "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.id IN (%s) AND cr.status='pending' ORDER BY cr.id" % зн,
    list(партия)).fetchall()
шаг = max(1, len(строки) // max(1, СКОЛЬКО))
взято = [строки[i] for i in range(СДВИГ, len(строки), шаг)][:СКОЛЬКО]
print("в очереди %d, показываю %d (сдвиг %d, шаг %d)"
      % (len(строки), len(взято), СДВИГ, шаг))
for r in взято:
    п = {}
    try:
        п = (json.loads(r["panel_json"] or "{}") or {}).get("vtoroy_adres") or {}
    except Exception:                                            # noqa: BLE001
        pass
    print("=" * 72)
    print("rev %s | %s | %s" % (r["id"], r["email"], r["company_name"]))
    print("роль адреса: %s | первое письмо: %s | контакт: %s"
          % (п.get("rol"), п.get("pervyy_adres"), r["contact_name"]))
    print("ТЕМА: %s" % r["subject"])
    print("-" * 72)
    print(r["body"])
c.close()
