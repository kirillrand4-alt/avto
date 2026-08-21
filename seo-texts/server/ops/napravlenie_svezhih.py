# -*- coding: utf-8 -*-
"""Направление у СВЕЖИХ писем (последние сутки-трое), включая неотправленные.

Отправленные сегодня уже проверены - там сходится. Регрессия «направление
пишется не то» проявилась бы прежде всего на том, что генерировалось
последним и ещё стоит в очереди. Сверяем три показания:
  письмо (panel_json.letter.division) / кампания / метка компании,
плюс ГОЛОС ТЕЛА - кем письмо представляется получателю.
"""
import json
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT cr.id, cr.campaign_id, cr.status, cr.email, cr.subject, cr.created_at,"
    "       COALESCE(cr.panel_json,'') AS pj, COALESCE(cr.body,'') AS body "
    "  FROM confirm_reviews cr "
    " WHERE cr.created_at >= '2026-08-18' ORDER BY cr.created_at"
).fetchall()
print(f"писем создано с 18.08: {len(строки)}")

почему = Counter(); пары = Counter(); голоса = Counter()
плохо = []
for р in строки:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                              # noqa: BLE001
        п = {}
    L = п.get("letter") or {}
    K = п.get("company") or {}
    д = str(L.get("division") or п.get("letter_division") or "")
    пч = str(L.get("division_reason") or п.get("letter_division_reason") or "")
    метка = str(K.get("division") or "")
    камп = "kc" if int(р["campaign_id"] or 0) in (9, 10) else "meyer"
    тело = str(р["body"] or "") + " " + str(р["subject"] or "")
    голос = ("kc" if re.search(r"Компрессор\s*Центр", тело, re.I) else
             "meyer" if re.search(r"Meyer|Мейер", тело, re.I) else "")
    почему[пч or "нет"] += 1
    пары[f"{д or '?'} / камп {камп}"] += 1
    голоса[f"{д or '?'} / голос {голос or '-'}"] += 1
    беда = []
    if д and д != камп:
        беда.append("письмо≠кампания")
    if д and метка and метка != д and "+" not in метка:
        беда.append("письмо≠метка")
    if д and голос and голос != д:
        беда.append("письмо≠голос тела")
    if беда:
        плохо.append((р["id"], р["created_at"], р["status"], д, камп, метка,
                      голос, ", ".join(беда), р["subject"]))

print("\nобоснование:", dict(почему))
print("письмо/кампания:", dict(пары))
print("письмо/голос тела:", dict(голоса))
print(f"\nрасхождений: {len(плохо)}")
for r in плохо[:25]:
    print(f"  №{r[0]} {r[1][:16]} {r[2]:<9} письмо={r[3]} камп={r[4]} "
          f"метка={r[5] or '-'} голос={r[6] or '-'} :: {r[7]}")
    print(f"       {str(r[8])[:72]}")
