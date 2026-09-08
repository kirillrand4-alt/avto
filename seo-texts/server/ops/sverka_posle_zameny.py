# -*- coding: utf-8 -*-
"""Сверка после замены: везде ли новый текст и не разошлись ли места."""
import json, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
МЕТКА = "удаление эгилопса и овсюга"          # есть только в новом тексте
store = Store(r"C:\sender\sender.db")
счёт = Counter()
беда = []
with store._lock:
    for р in store._conn.execute(
            """SELECT c.id, c.status AS cst, c.body, c.panel_json,
                      m.status AS mst, m.body_rendered
                 FROM confirm_reviews c LEFT JOIN messages m
                      ON c.message_id = m.id
                WHERE c.subject=?""", (ТЕМА,)):
        отпр = str(р["cst"]) == "sent" or str(р["mst"] or "") == "sent"
        нов_карт = МЕТКА in str(р["body"] or "")
        try:
            пан = json.loads(р["panel_json"] or "{}").get("letter") or {}
        except Exception:                                       # noqa: BLE001
            пан = {}
        нов_пан = МЕТКА in str(пан.get("body") or "")
        нов_фин = МЕТКА in str(пан.get("final_body") or "")
        тело_п = str(р["body_rendered"] or "")
        нов_письмо = (МЕТКА in тело_п) if тело_п.strip() else None
        if отпр:
            счёт["отправленные (не трогали)"] += 1
            continue
        if нов_карт and нов_пан and нов_фин and нов_письмо is not False:
            счёт["всё сходится"] += 1
        else:
            счёт["РАСХОЖДЕНИЕ"] += 1
            беда.append((р["id"], str(р["cst"]), str(р["mst"] or "-"),
                         нов_карт, нов_пан, нов_фин, нов_письмо))
        if "\u2014" in str(р["body"] or ""):
            счёт["длинное тире в теле"] += 1
for i, cst, mst, k, p, f, w in беда[:12]:
    print("   карточка %-7s %-9s письмо %-14s тело=%s панель=%s финал=%s "
          "собранное=%s" % (i, cst, mst, k, p, f, w))
print("")
print("=" * 70)
print("=== СВЕРКА ПОСЛЕ ЗАМЕНЫ ===")
for к, в in счёт.most_common():
    print("   %-30s %5d" % (к, в))
