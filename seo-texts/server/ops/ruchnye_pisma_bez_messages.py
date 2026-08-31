# -*- coding: utf-8 -*-
"""Ручные письма панели: заводится ли им строка в messages.

approve() падает «нет message_id», если письмо не заведено в messages.
Генерация заводит его сама (AiQuota._ensure_message), а /confirm/novoe —
нет. Проверяем, сколько таких карточек и уходили ли они вообще.
"""
import json
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
ручные = []
for r in c.execute("SELECT id, status, email, message_id, panel_json,"
                   "       substr(created_at,1,16) c FROM confirm_reviews"
                   " WHERE panel_json LIKE '%ruchnoe_pismo%'"
                   " ORDER BY id DESC LIMIT 40"):
    ручные.append(dict(r))
print("=== РУЧНЫЕ ПИСЬМА (panel.ruchnoe_pismo) ===")
print("   найдено: %d" % len(ручные))
без_письма = [r for r in ручные if r["message_id"] is None]
print("   из них без строки в messages: %d" % len(без_письма))
for r in ручные[:12]:
    print("   %6s %-10s msg=%-7s %-28s %s"
          % (r["id"], r["status"], r["message_id"], (r["email"] or "")[:28],
             r["c"]))

print("\n=== СТАТУСЫ РУЧНЫХ ===")
from collections import Counter
print("   %s" % dict(Counter(r["status"] for r in ручные)))
ушли = [r for r in ручные if r["status"] == "sent"]
print("   ушло: %d; из них с message_id: %d"
      % (len(ушли), sum(1 for r in ушли if r["message_id"])))
c.close()
print("\n=== ИТОГ ===")
print("если все ручные висят без message_id и ни одно не ушло —")
print("кнопка «новое письмо» в панели доводит до очереди, но не до отправки.")
