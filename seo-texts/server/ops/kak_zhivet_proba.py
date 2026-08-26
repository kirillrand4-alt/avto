# -*- coding: utf-8 -*-
"""Настройки и состояние ProbeSync: включён ли, что публиковал в последний раз."""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r"C:\sender")
т = io.open(r"C:\sender\sender.yaml", encoding="utf-8", errors="replace").read()
печать = False
for с in т.splitlines():
    if re.match(r"^\s*probe", с) or "probe" in с.lower():
        print("   " + с.rstrip()[:150])

print("")
print("=== файлы обмена с работником на дропе ===")
import urllib.request
url = os.environ.get("DROP_URL", "")
tok = os.environ.get("DROP_TOKEN", "")
if url and tok:
    try:
        req = urllib.request.Request(url.rstrip("/") + "/list",
                                     headers={"X-Drop-Token": tok})
        д = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        имена = д if isinstance(д, list) else д.get("files") or []
        for ф in имена:
            имя = ф if isinstance(ф, str) else (ф.get("name") or "")
            if "probe" in имя.lower() or "proba" in имя.lower():
                размер = "" if isinstance(ф, str) else " %s б" % ф.get("size")
                когда = "" if isinstance(ф, str) else "  %s" % ф.get("mtime", "")
                print("   %-46s%s%s" % (имя, размер, когда))
    except Exception as ex:                                   # noqa: BLE001
        print("   дроп не ответил: %r" % ex)
else:
    print("   DROP_URL/DROP_TOKEN не в окружении этого процесса")

print("")
print("=== панельные настройки пробы ===")
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
try:
    for r in c.execute("SELECT key, value FROM panel_settings "
                       "WHERE key LIKE '%probe%' OR key LIKE '%proba%'"):
        print("   %-34s %s" % (r[0], str(r[1])[:80]))
except Exception as ex:                                       # noqa: BLE001
    print("   panel_settings: %s" % ex)
c.close()
