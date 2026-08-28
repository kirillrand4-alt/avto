# -*- coding: utf-8 -*-
"""Лиды «не интересно», в которых на самом деле зовут подать заявку."""
import re
import sqlite3
from collections import Counter

ЗОВУТ = re.compile(
    r"(?i)(заполн\w*\s+форм|форм\w*\s+обратной|заявк\w*\s+на\s+партнёр|"
    r"заявк\w*\s+на\s+партнер|стать\s+поставщик|аккредит|"
    r"регистрац\w*\s+(?:на|в)\s+портал|тендерн\w*\s+площадк|"
    r"внесения\s+его\s+в\s+базу|коммерческое\s+предложение\s+"
    r"(?:направ|приш|отправ)|пришлите\s+(?:кп|коммерческое)|"
    r"направьте\s+(?:кп|коммерческое)|прайс)")
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
всего = Counter()
нашли = []
for r in c.execute("SELECT id, status, reply_kind, email, company_name, need, "
                   "       created_at FROM leads ORDER BY id"):
    всего[str(r["status"])] += 1
    т = str(r["need"] or "")
    if str(r["status"]) in ("not_interested",) and ЗОВУТ.search(т):
        нашли.append((r["id"], r["email"], str(r["company_name"] or "")[:30],
                      str(r["created_at"])[:10], ЗОВУТ.search(т).group(0)[:40],
                      т[:120]))
print("лидов всего: %d" % sum(всего.values()))
for к, n in всего.most_common():
    print("   %-18s %4d" % (к, n))
print("")
print("=== помечены «не интересно», а на деле зовут подать заявку: %d ===" % len(нашли))
for i, e, к, д, ф, т in нашли:
    print("   лид #%-4s %-26s %-30s %s" % (i, str(e)[:26], к, д))
    print("      зацепка: «%s»" % ф)
    print("      текст: %s" % т.replace("\n", " ")[:112])
c.close()
