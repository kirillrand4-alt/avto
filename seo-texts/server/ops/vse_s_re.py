# -*- coding: utf-8 -*-
"""Владелец 03.11 «давай все с ре оставим»: pending-напоминаниям вернуть «Re:». [--primenit]"""
import re, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
р = c.execute("SELECT id, subject FROM confirm_reviews WHERE kind='reply' AND status='pending' "
              "AND panel_json LIKE '%napominanie%' AND subject NOT LIKE 're:%'").fetchall()
print("pending напоминаний без Re:", len(р))
if "--primenit" in sys.argv:
    with c:
        c.executemany("UPDATE confirm_reviews SET subject=? WHERE id=? AND status='pending'",
                      [("Re: " + re.sub(r"^(?:re:\s*)+", "", s or "", flags=re.I), i) for i, s in р])
    print("применено")
