# -*- coding: utf-8 -*-
"""Снятия «уже писали» после момента (UTC): uzhe_pisali_posle.py 2026-10-14T03:48"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
т = sys.argv[1]
print("после %s UTC: %s" % (т, c.execute("SELECT count(*) FROM messages WHERE status='skipped' AND last_error LIKE "
      "'auto_send:уже писали%%' AND updated_at >= ?", (т,)).fetchone()[0]))
print("последние:", c.execute("SELECT id, updated_at, last_error FROM messages WHERE last_error LIKE 'auto_send:уже писали%' "
      "ORDER BY updated_at DESC LIMIT 3").fetchall())
print("=== ПОСЛЕ ===")
