# -*- coding: utf-8 -*-
"""Компании групп «Россия 9000»/«Белорусь 1000» со статусом «снято с очереди»
(письма были, ни одно не ушло и не стоит в очереди) и «сбой отправки»: почему
сняли. Владелец 14.10: «распознай» — вернуть только снятых по технической
причине. Только чтение; результат — _ops/snyatye-gruppy.json (+ дроп)."""
import json
import shutil
import sqlite3
from collections import Counter, defaultdict

ГР = ("Россия 9000", "Белорусь 1000")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
кампания = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
рид = {}
for r in c.execute("SELECT id, inn, extra_json FROM recipients WHERE inn IS NOT NULL"):
    for г in ГР:
        if г in str(r["extra_json"] or ""):
            рид[r["id"]] = (str(r["inn"]), г)
лиды = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
по_инн = defaultdict(list)
for m in c.execute("SELECT id, recipient_id, campaign_id, status, last_error, updated_at FROM messages"):
    if m["recipient_id"] in рид:
        по_инн[рид[m["recipient_id"]][0]].append(dict(m))
ЖИВ = {"pending_review", "approved", "scheduled", "sending", "sent"}
итог = []
for inn, мм in по_инн.items():
    ст = {m["status"] for m in мм}
    if ст & ЖИВ or inn in лиды:
        continue
    for m in мм:
        рв = c.execute("SELECT id, email, status, reason, decided_by, decided_at FROM confirm_reviews "
                       "WHERE message_id=? ORDER BY id DESC LIMIT 1", (m["id"],)).fetchone()
        итог.append({"inn": inn, "группа": рид[m["recipient_id"]][1], "message_id": m["id"],
                     "кампания": кампания.get(m["campaign_id"]), "статус_письма": m["status"],
                     "ошибка": (m["last_error"] or "")[:200], "review_id": рв and рв["id"],
                     "email": рв and рв["email"], "статус_карточки": рв and рв["status"],
                     "причина": рв and (рв["reason"] or "")[:200], "кто": рв and рв["decided_by"],
                     "когда": (рв and рв["decided_at"]) or m["updated_at"]})
json.dump(итог, open(r"C:\sender\_ops\snyatye-gruppy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
shutil.copy2(r"C:\sender\_ops\snyatye-gruppy.json", r"C:\seostat\drop\drop-storage\ops_snyatye-gruppy.json")
print("компаний: %d, писем: %d" % (len({x["inn"] for x in итог}), len(итог)))
print(Counter((x["статус_письма"], x["статус_карточки"], x["кто"]) for x in итог).most_common(20))
print("=== СНЯТЫЕ ГРУППЫ ===")
