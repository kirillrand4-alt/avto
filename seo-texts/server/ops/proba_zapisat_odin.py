# -*- coding: utf-8 -*-
"""Вызвать probe_enrich.записать на одном адресе и посмотреть, что вернёт."""
import logging
import os
import sqlite3
import sys

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
sys.path.insert(0, r"C:\sender")
from sender import probe_enrich                               # noqa: E402

print("модуль: %s" % probe_enrich.__file__)
путь = r"C:\sender\enrich.db"
print("существует: %s" % os.path.exists(путь))

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
а, в, отв = c.execute(
    "SELECT email, verdict, answer FROM addr_probe "
    " WHERE verdict IN ('нет ящика','нет MX') LIMIT 1").fetchone()
c.close()
print("адрес: %s / %s" % (а, в))
итог = probe_enrich.записать(путь, [{"email": а, "verdict": в, "answer": отв}])
print("итог: %s" % итог)

o = sqlite3.connect(путь, timeout=60)
print("в базе теперь: %s" % o.execute(
    "SELECT probe_verdict, probe_ts FROM emails WHERE lower(email)=?",
    (а,)).fetchall())
o.close()
