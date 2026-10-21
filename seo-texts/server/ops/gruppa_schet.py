# -*- coding: utf-8 -*-
"""Сколько адресов в группе: gruppa_schet.py "<группа>" """
import json
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
г = sys.argv[1]
n = 0
for (ex,) in c.execute("SELECT extra_json FROM recipients WHERE extra_json LIKE ?", ("%" + г + "%",)):
    if г in (json.loads(ex or "{}").get("gruppy") or []):
        n += 1
print("в группе «%s»: %d" % (г, n))
