# -*- coding: utf-8 -*-
"""Владелец 03.11 «сделай без Re»: у pending-напоминаний убрать «Re:» из темы. [--primenit]"""
import re, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
р = c.execute("SELECT id, subject FROM confirm_reviews WHERE kind='reply' AND status='pending' "
              "AND panel_json LIKE '%napominanie%' AND subject LIKE 're:%'").fetchall()
print("pending напоминаний с Re:", len(р))
for i, s in р[:3]:
    print("  ", s, "→", re.sub(r"^(?:re:\s*)+", "", s, flags=re.I))
if "--primenit" in sys.argv:
    with c:
        for i, s in р:
            c.execute("UPDATE confirm_reviews SET subject=? WHERE id=? AND status='pending'", (re.sub(r"^(?:re:\s*)+", "", s, flags=re.I), i))
    print("применено")
