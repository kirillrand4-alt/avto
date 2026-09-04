# -*- coding: utf-8 -*-
"""Только чтение: стартует ли цикл автоотправки и с каким sender."""
import datetime as dt
import io
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

print("=== КАК СОБИРАЮТ Deps И ЦИКЛ ===")
т = io.open(r"C:\sender\sender\wiring.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
for м in re.finditer(r"live_sender|return Deps|Deps\(", т):
    н = т[:м.start()].count("\n")
    print("  wiring.py:%4d| %s" % (н + 1, лн[н].strip()[:96]))
т2 = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8", errors="replace").read()
лн2 = т2.splitlines()
print()
for м in re.finditer(r"_auto_send|live_sender", т2):
    н = т2[:м.start()].count("\n")
    print("  app.py:%4d| %s" % (н + 1, лн2[н].strip()[:96]))

cfg = Config.load(r"C:\sender\sender.yaml")
print("\n  confirm.live_send = %s" % cfg.get("confirm.live_send", None))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
мск = dt.datetime.now()
print("\n=== ДВИЖЕНИЕ В БАЗЕ ЗА 10 МИНУТ ===")
п = (мск - dt.timedelta(minutes=10)).isoformat()
n = c.execute("SELECT COUNT(*) FROM messages WHERE updated_at>=?", (п,)).fetchone()[0]
print("  писем тронуто: %d" % n)
print("  сейчас %s МСК" % мск.strftime("%H:%M:%S"))
