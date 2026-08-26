# -*- coding: utf-8 -*-
"""Оставшиеся без вердикта в обогащении: есть ли они там вообще."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
приг = {r[0] for r in c.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
c.close()
o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
сверд = {r[0] for r in o.execute(
    "SELECT lower(email) FROM emails WHERE probe_verdict IN ('нет ящика','нет MX')")}
все = {r[0] for r in o.execute("SELECT lower(email) FROM emails")}
o.close()
осталось = приг - сверд
print("приговоров: %d | с вердиктом в обогащении: %d | осталось: %d"
      % (len(приг), len(приг & сверд), len(осталось)))
нет_вовсе = осталось - все
print("из оставшихся НЕТ в таблице emails вовсе: %d" % len(нет_вовсе))
print("есть в emails, но вердикт не проставлен: %d" % len(осталось & все))
for а in list(осталось & все)[:8]:
    print("   %s" % а)
