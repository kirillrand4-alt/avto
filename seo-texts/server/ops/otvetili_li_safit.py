# -*- coding: utf-8 -*-
"""Ответил ли «Сафит» на наш ответ — и жив ли перезапущенный блок."""
import json
import sqlite3
import subprocess

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("=== ВСЯ ПЕРЕПИСКА С «САФИТ» ===")
for р in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.subject "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.email LIKE '%safit.su%' ORDER BY m.sent_at"):
    print("   письмо #%-6s %-8s %s с %s"
          % (р["id"], р["status"], str(р["sent_at"])[:19], р["mailbox_id"]))
    print("      тема: %s" % р["subject"])

print("\n=== ВХОДЯЩИЕ ОТ НИХ ===")
for р in c.execute(
        "SELECT ев.id, ев.event_ts, ев.event_type, ев.detail_json FROM events ев "
        "  LEFT JOIN recipients r ON r.id=ев.recipient_id "
        " WHERE (r.email LIKE '%safit.su%' OR ев.detail_json LIKE '%safit.su%') "
        "   AND ев.event_type IN ('reply','reply_auto','other','reply_sent') "
        " ORDER BY ев.id"):
    d = json.loads(р["detail_json"] or "{}")
    з = d.get("headers") or {}
    print("   #%-7s %s %-11s от %s"
          % (р["id"], str(р["event_ts"])[:19], р["event_type"],
             str(з.get("From") or d.get("komu") or "-")[:44]))
    т = " ".join(str(d.get("snippet") or d.get("tema") or "").split())
    if т:
        print("      %s" % т[:150])

print("\n=== КАРТОЧКА В ЛЕНТЕ ===")
for р in c.execute("SELECT id, email, company_name, reply_kind, status, "
                   "       substr(need,1,120) need FROM leads "
                   " WHERE email LIKE '%safit.su%'"):
    print("   #%s %s | %s | %s | %s" % (р["id"], р["email"], р["company_name"],
                                        р["reply_kind"], р["status"]))
    print("      %s" % р["need"])

print("\n=== ПРОЦЕССЫ ГЕНЕРАЦИИ ===")
в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
     "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
if т:
    д = json.loads(т)
    for п in (д if isinstance(д, list) else [д]):
        print("   pid %s: %s" % (п["ProcessId"], str(п["CommandLine"])[:130]))
else:
    print("   НЕТ процессов генерации")
