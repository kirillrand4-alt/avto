# -*- coding: utf-8 -*-
"""Полная карточка 12575: чем её мог отрезать фильтр очереди."""
import json
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM confirm_reviews WHERE id=12575").fetchone()
for к in r.keys():
    v = r[к]
    if к in ("body", "edited_body", "panel_json", "diff_text"):
        continue
    print("   %-18s %s" % (к, str(v)[:90]))
пж = {}
try:
    пж = json.loads(r["panel_json"] or "{}") or {}
except Exception:                                             # noqa: BLE001
    pass
print("\n   panel_json ключи: %s" % sorted(пж.keys())[:14])
комп = пж.get("company") or {}
print("   panel.company.division: %r" % комп.get("division"))
print("   panel.company.name:     %r" % комп.get("name"))
print("   тело (первые 200): %s" % str(r["body"] or "")[:200].replace("\n", " "))

rid = r["recipient_id"]
print("\n   recipient_id: %s" % rid)
if rid:
    q = c.execute("SELECT id, segment, company_name, inn, email, extra_json"
                  "  FROM recipients WHERE id=?", (rid,)).fetchone()
    if q:
        доп = {}
        try:
            доп = json.loads(q["extra_json"] or "{}") or {}
        except Exception:                                     # noqa: BLE001
            pass
        print("   получатель: %s | segment=%r | группы=%s"
              % (q["company_name"], q["segment"],
                 str(доп.get("gruppy"))[:80]))
    else:
        print("   получателя с таким id НЕТ")
else:
    print("   получатель не привязан — фильтр по группе такую карточку уронит")
c.close()
print("\n=== ИТОГ ===")
print("очередь сортирует ответы наверх, но фильтры направления и группы")
print("применяются ПОСЛЕ сортировки — если в панели выбран фильтр,")
print("карточка без направления/группы из выдачи выпадает.")
