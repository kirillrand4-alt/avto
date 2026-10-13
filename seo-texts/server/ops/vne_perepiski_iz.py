# -*- coding: utf-8 -*-
"""Входящее «вне переписки» #id: From/To/Subject и кандидаты на компанию."""
import json
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (int(sys.argv[1]),)).fetchone()
d = json.loads(е["detail_json"] or "{}")
h = d.get("headers") or {}
for к in ("From", "To", "Cc", "Subject", "Date", "Reply-To"):
    print("%s: %s" % (к, h.get(к)))
от = str(h.get("From") or "")
import re
адрес = (re.findall(r"[\w.+-]+@[\w.-]+", от) or [""])[0].lower()
дом = адрес.rsplit("@", 1)[-1]
print("адрес: %s" % адрес)
for р in c.execute("SELECT id, company_name, inn, email FROM recipients WHERE lower(email)=? OR (domain=? AND domain NOT IN "
                   "('gmail.com','mail.ru','yandex.ru','bk.ru','list.ru','inbox.ru','ya.ru'))", (адрес, дом)):
    print("   получатель с этим адресом/доменом: #%s %s ИНН %s <%s>" % tuple(р))
print("=== ВНЕ ПЕРЕПИСКИ: ИЗ ===")
