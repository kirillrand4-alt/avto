# -*- coding: utf-8 -*-
"""Включена ли автоотправка (panel_settings), когда переключали; окно. Только чтение."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
кол = [r[1] for r in c.execute("PRAGMA table_info(panel_settings)")]
print(кол)
for r in c.execute("SELECT * FROM panel_settings WHERE key LIKE '%auto%' OR key LIKE '%window%' OR key LIKE '%pause%' OR key LIKE '%stop%'"): print([str(x)[:200] for x in r])
try: print("аудит:", c.execute("SELECT * FROM audit_log WHERE created_at>=datetime('now','-6 hours') ORDER BY id DESC LIMIT 15").fetchall())
except Exception as ex: print(ex)
