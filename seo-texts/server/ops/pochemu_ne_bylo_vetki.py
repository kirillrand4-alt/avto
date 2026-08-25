# -*- coding: utf-8 -*-
"""Почему у потерянных ответов не было ветки — по заголовкам, а не на слух.

Карточка заводилась только при непустом thread_id, а он берётся так:
Thread-ID / X-Thread-ID, иначе хеш первого References, иначе хеш
In-Reply-To. Пусто — значит в письме не было НИ ОДНОГО из трёх. Проверяем
это по сохранённым заголовкам тех самых пятнадцати.
"""
import json
import sqlite3
from collections import Counter

ПОТЕРЯШКИ = (58527, 67738, 69032, 69051, 70117, 72828, 80750, 82184, 82377,
             82622, 82732, 83270, 83386, 101864, 182154)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
места = ",".join("?" * len(ПОТЕРЯШКИ))

сводка = Counter()
print("=== ЗАГОЛОВКИ ПОТЕРЯННЫХ ОТВЕТОВ ===")
for р in c.execute("SELECT id, detail_json FROM events WHERE id IN (%s)" % места,
                   ПОТЕРЯШКИ):
    d = json.loads(р["detail_json"] or "{}")
    з = d.get("headers") or {}
    есть = [к for к in ("Thread-ID", "X-Thread-ID", "References", "In-Reply-To")
            if str(з.get(к) or "").strip()]
    почтовик = str(з.get("From") or "").split("@")[-1].strip("> ").lower()
    сводка["+".join(есть) or "НИ ОДНОГО"] += 1
    print("   #%-7s %-24s %s" % (р["id"], почтовик[:24],
                                 "+".join(есть) or "ни одного из трёх"))

print("\n=== ИТОГ ===")
for к, н in сводка.most_common():
    print("   %-28s %3d" % (к, н))

# Для сравнения — те ответы, что карточку получили.
print("\n=== ДЛЯ СРАВНЕНИЯ: ОТВЕТЫ С КАРТОЧКОЙ ===")
хорошо = Counter()
for р in c.execute(
        "SELECT ев.detail_json FROM events ев "
        "  JOIN leads l ON l.recipient_id=ев.recipient_id "
        " WHERE ев.event_type IN ('reply','reply_auto') "
        "   AND ев.id NOT IN (%s) LIMIT 200" % места, ПОТЕРЯШКИ):
    d = json.loads(р["detail_json"] or "{}")
    з = d.get("headers") or {}
    есть = [к for к in ("Thread-ID", "X-Thread-ID", "References", "In-Reply-To")
            if str(з.get(к) or "").strip()]
    хорошо["+".join(есть) or "НИ ОДНОГО"] += 1
for к, н in хорошо.most_common(6):
    print("   %-28s %3d" % (к, н))
