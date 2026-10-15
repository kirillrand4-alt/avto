# -*- coding: utf-8 -*-
"""Снять паузу с указанных ящиков: snyat_pauzu.py <ящик> [<ящик>...]"""
import sqlite3
import sys
import time
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    for м in sys.argv[1:]:
        n = c.execute("UPDATE mailbox_state SET paused=0, pause_reason=NULL, updated_at=? WHERE mailbox_id=?",
                      (time.strftime("%Y-%m-%dT%H:%M:%S"), м)).rowcount
        print("снята пауза: %s (%d)" % (м, n))
print("=== СНЯТЬ ПАУЗУ ===")
