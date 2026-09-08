# -*- coding: utf-8 -*-
"""На какое время назначены ждущие письма и работает ли тот, кто их шлёт."""
import subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)

def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None

когда = Counter()
самое_раннее = самое_позднее = None
with store._lock:
    for р in store._conn.execute(
            "SELECT scheduled_at, updated_at FROM messages WHERE status='scheduled'"):
        d = разбор(р["scheduled_at"])
        if d is None:
            когда["время не задано"] += 1
            continue
        самое_раннее = d if самое_раннее is None or d < самое_раннее else самое_раннее
        самое_позднее = d if самое_позднее is None or d > самое_позднее else самое_позднее
        когда["СРОК НАСТУПИЛ" if d <= теперь else "ждёт своего часа"] += 1
    посл = store._conn.execute(
        "SELECT MAX(sent_at) m FROM messages WHERE status='sent'").fetchone()["m"]
    в_sending = store._conn.execute(
        "SELECT id, mailbox_id, claimed_at FROM messages WHERE status='sending' "
        " LIMIT 8").fetchall()

print("сейчас UTC %s" % теперь.strftime("%Y-%m-%d %H:%M"))
for к, в in когда.most_common():
    print("   %-18s %5d" % (к, в))
print("самое раннее назначение: %s" % самое_раннее)
print("самое позднее назначение: %s" % самое_позднее)
print("последняя реальная отправка: %s" % посл)
print("")
print("--- застрявшие в sending ---")
for р in в_sending:
    print("   письмо %-7s ящик %-30s взято %s"
          % (р["id"], str(р["mailbox_id"] or "?")[:30], р["claimed_at"]))

print("")
print("--- службы и задания ---")
for ком, имя in (
        ("Get-Service SenderPanel | Select-Object Name,Status | Format-List",
         "служба панели"),
        ("Get-ScheduledTask | Where-Object {$_.TaskName -like '*sender*'} | "
         "Select-Object TaskName,State | Format-List", "задания планировщика")):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       capture_output=True, timeout=120)
    т = (r.stdout or b"").decode("cp866", errors="replace")
    if not т.strip():
        т = (r.stdout or b"").decode("utf-8", errors="replace")
    print("=== %s ===" % имя)
    print(т.strip()[:1200])
