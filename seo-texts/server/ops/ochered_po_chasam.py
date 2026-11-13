# -*- coding: utf-8 -*-
"""Очередь автоотправки: scheduled по часу срока (UTC) и по состоянию ящика; служба; последний проход. Только чтение."""
import sqlite3, subprocess
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
пауз = {r[0] for r in c.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
сч = Counter()
for mb, s in c.execute("SELECT mailbox_id, substr(scheduled_at,1,13) FROM messages WHERE status='scheduled'"):
    сч[(s, "пауза" if mb in пауз else ("без ящика" if not mb else "ок"))] += 1
print("сейчас UTC:", c.execute("SELECT datetime('now')").fetchone()[0])
for к in sorted(сч): print("  ", к, сч[к])
print(subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Service SenderPanel).Status; (Get-CimInstance Win32_Process | ? {$_.Name -eq 'python.exe' -and $_.CommandLine -like '*sender*serve*' -or $_.CommandLine -like '*uvicorn*'} | select -First 2 | % { $_.CreationDate })"], capture_output=True, text=True, errors="replace").stdout)
