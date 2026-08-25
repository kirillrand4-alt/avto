# -*- coding: utf-8 -*-
"""Какая метка разбора стояла у потерянных ответов — и у тех, что дошли.

Ветка у всех пятнадцати была (References+In-Reply-To), значит дело не в
ней. Следующий подозреваемый — сам разбор: в _handle_reply есть ветка
«unsub_request → return, отказ не лид», она отрабатывает ДО заведения
карточки.
"""
import json
import sqlite3
from collections import Counter

ПОТЕРЯШКИ = (58527, 67738, 69032, 69051, 70117, 72828, 80750, 82184, 82377,
             82622, 82732, 83270, 83386, 101864, 182154)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
места = ",".join("?" * len(ПОТЕРЯШКИ))

print("=== МЕТКИ ПОТЕРЯННЫХ ===")
метки = Counter()
for р in c.execute("SELECT id, event_type, recipient_id, detail_json FROM events "
                   " WHERE id IN (%s) ORDER BY id" % места, ПОТЕРЯШКИ):
    d = json.loads(р["detail_json"] or "{}")
    м = str(d.get("reply_kind") or "нет метки")
    метки[м] += 1
    print("   #%-7s %-10s получатель %-7s метка %-16s %s"
          % (р["id"], р["event_type"], р["recipient_id"] or "НЕТ", м,
             " ".join(str(d.get("snippet") or "").split())[:40]))
print("   ---")
for к, н in метки.most_common():
    print("   %-18s %3d" % (к, н))

print("\n=== МЕТКИ ТЕХ, КОМУ КАРТОЧКА ДОСТАЛАСЬ ===")
дошли = Counter()
for р in c.execute(
        "SELECT DISTINCT ев.id, ев.detail_json FROM events ев "
        "  JOIN leads l ON l.recipient_id=ев.recipient_id "
        " WHERE ев.event_type IN ('reply','reply_auto') "
        "   AND ев.id NOT IN (%s)" % места, ПОТЕРЯШКИ):
    d = json.loads(р["detail_json"] or "{}")
    дошли[str(d.get("reply_kind") or "нет метки")] += 1
for к, н in дошли.most_common(8):
    print("   %-18s %3d" % (к, н))

print("\n=== МЕТКИ В САМИХ КАРТОЧКАХ ЛЕНТЫ ===")
for р in c.execute("SELECT COALESCE(reply_kind,'нет') м, COUNT(*) n FROM leads "
                   " GROUP BY м ORDER BY n DESC"):
    print("   %-18s %3d" % (р["м"], р["n"]))
