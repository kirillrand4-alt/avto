# -*- coding: utf-8 -*-
import json, re, sqlite3, sys
print("кодировка вывода: %s, файла: %s" % (sys.stdout.encoding, sys.getdefaultencoding()))
ПРИМЕТА = re.compile("[\u0420\u0421][\u0400-\u04FF\u2000-\u20FF\u2100-\u21FF]")
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT detail_json FROM events WHERE id=308518").fetchone()
d = json.loads(r["detail_json"] or "{}")
т = str(d.get("snippet") or "")
print("длина: %d" % len(т))
print("первые 40 кодов: %s" % [hex(ord(x)) for x in т[:40]])
print("совпадений приметы: %d" % len(ПРИМЕТА.findall(т[:400])))
try:
    print("расшифровка: %s" % т.encode("cp1251").decode("utf-8")[:80])
except Exception as ex:
    print("расшифровка не вышла: %s" % ex)
c.close()
