# -*- coding: utf-8 -*-
"""Совпадают ли серверные probe_enrich/probe_sync с нашей веткой до правки."""
import hashlib
import io

for п in (r"C:\sender\sender\probe_enrich.py", r"C:\sender\sender\probe_sync.py"):
    б = io.open(п, "rb").read()
    т = б.decode("utf-8", "replace")
    print("%-42s %7d б  sha1 %s" % (п.rsplit("\\", 1)[-1], len(б),
                                    hashlib.sha1(б).hexdigest()))
    print("      строк %d | busy_timeout: %s | ПОД ЗАМКОМ: %s"
          % (т.count("\n"), "busy_timeout" in т, "ПОД ЗАМКОМ STORE" in т))
