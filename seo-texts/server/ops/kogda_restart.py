# -*- coding: utf-8 -*-
import json, os, sqlite3, subprocess
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$p=(Get-CimInstance Win32_Service -Filter \"Name='SenderPanel'\").ProcessId; "
         "if($p){(Get-Process -Id $p | Select-Object Id,StartTime | ConvertTo-Json -Compress)}"],
        capture_output=True, text=True, timeout=45)
    print("SenderPanel: %s" % (out.stdout or out.stderr).strip()[:200])
except Exception as e:
    print("не спросил: %s" % str(e)[:90])
print("время файла imap_watcher.py: %s"
      % __import__("time").strftime("%Y-%m-%d %H:%M",
                                    __import__("time").localtime(
                                        os.path.getmtime(r"C:\sender\sender\imap_watcher.py"))))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("")
print("=== входящие сегодня: привязались или нет, по часам ===")
for r in c.execute(
        "SELECT substr(event_ts,12,2) ч, "
        "       SUM(CASE WHEN recipient_id IS NULL THEN 1 ELSE 0 END) без, "
        "       SUM(CASE WHEN recipient_id IS NOT NULL THEN 1 ELSE 0 END) с "
        "  FROM events WHERE substr(event_ts,1,10)=date('now') "
        "   AND event_type IN ('reply','reply_auto','other','bounce') "
        " GROUP BY 1 ORDER BY 1"):
    print("   %s:00 UTC   без привязки %3d   с привязкой %3d" % (r["ч"], r["без"], r["с"]))
c.close()
