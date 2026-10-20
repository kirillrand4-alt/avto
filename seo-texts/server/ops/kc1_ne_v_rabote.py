# -*- coding: utf-8 -*-
"""КЦ-1: кто НЕ попадает в генерацию и почему (владелец 20.10). Разрез:
без ИНН (что в inn_raw), сегмент не «кц» (какой), уже писали."""
import json
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
без_инн, не_кц, сег = [], [], Counter()
писали = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM send_log WHERE inn IS NOT NULL")}
всего = 0
for rid, em, inn, seg, ex in c.execute("SELECT id, email, inn, segment, extra_json FROM recipients WHERE extra_json LIKE '%КЦ-1%'"):
    x = json.loads(ex or "{}")
    if "КЦ-1" not in (x.get("gruppy") or []):
        continue
    всего += 1
    if not inn:
        без_инн.append(str(x.get("inn_raw") or ""))
        continue
    if not (str(seg or "") == "кц" or x.get("target_division") == "kc"):
        не_кц.append(str(inn))
        сег[str(seg)] += 1
print("в группе КЦ-1:", всего)
print("без ИНН:", len(без_инн))
вид = Counter()
for v in без_инн:
    ц = re.sub(r"\D", "", v)
    вид["пусто" if not v.strip() else "9 цифр (УНП Беларуси?)" if len(ц) == 9 else "%d цифр" % len(ц) if ц else "текст"] += 1
print("  что в inn_raw:", вид.most_common(8))
print("  примеры:", без_инн[:12])
print("  текстовые примеры:", [v for v in без_инн if not re.sub(r"\D", "", v)][:15])
print("сегмент не КЦ:", len(не_кц), сег.most_common(8), "| из них уже писали:", sum(1 for i in не_кц if i in писали))
