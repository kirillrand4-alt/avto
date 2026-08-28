# -*- coding: utf-8 -*-
"""Что со службой после перезапуска и не залипло ли что-нибудь."""
import io
import os
import sqlite3
import subprocess
r = subprocess.run(["sc.exe", "queryex", "SenderPanel"], capture_output=True,
                   text=True, timeout=30)
состояние = pid = ""
for стр in (r.stdout or "").splitlines():
    if "STATE" in стр:
        состояние = стр.split(":")[-1].strip()
    if "PID" in стр:
        pid = стр.split(":")[-1].strip()
print("служба: %s | PID сейчас: %s" % (состояние, pid))
итог = r"C:\sender\_ops\perezapusk-itog.txt"
if os.path.exists(итог):
    print("отчёт отцепленного процесса: %s"
          % io.open(итог, encoding="utf-8-sig", errors="ignore").read().strip())
else:
    print("отчёт отцепленного процесса ещё не записан")
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
for ст in ("sending", "scheduled", "pending_review"):
    print("  %-16s %d" % (ст, c.execute(
        "SELECT COUNT(*) FROM messages WHERE status=?", (ст,)).fetchone()[0]))
c.close()
