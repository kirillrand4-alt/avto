# -*- coding: utf-8 -*-
"""Донести приговоры проб до обогащения: его читает отбор кандидатов."""
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
cfg = Config.load(r"C:\sender\sender.yaml")
из_конфига = cfg.get("service.enrich_db", None)
print("service.enrich_db = %r (существует: %s)"
      % (из_конфига, os.path.exists(str(из_конфига or ""))))
for п in (r"C:\sender\enrich.db", r"C:\sender\server\enrich.db"):
    print("   %-34s существует: %s" % (п, os.path.exists(п)))

путь = str(из_конфига or "")
if not os.path.exists(путь):
    путь = r"C:\sender\enrich.db"
print("пишем в: %s" % путь)

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = [dict(r) for r in c.execute(
    "SELECT email, verdict, answer FROM addr_probe "
    " WHERE verdict IN ('нет ящика','нет MX')")]
c.close()
print("приговоров к переносу: %d" % len(ряды))
if not ДЕЛАТЬ:
    print("\nвхолостую. Перенести — primenit")
    raise SystemExit(0)

from sender.probe_enrich import записать                      # noqa: E402
print("итог: %s" % записать(путь, ряды))
