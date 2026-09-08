# -*- coding: utf-8 -*-
"""Когда письма уходили на самом деле и что говорят гейты."""
import subprocess, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

часы = Counter()
дни = Counter()
with store._lock:
    for р in store._conn.execute(
            "SELECT sent_at FROM messages WHERE status='sent' "
            "  AND sent_at >= datetime('now','-5 days')"):
        т = str(р["sent_at"] or "").replace("T", " ")
        дни[т[:10]] += 1
        часы[т[:13]] += 1
print("--- отправлено по дням (5 дней) ---")
for к in sorted(дни):
    print("   %s  %5d" % (к, дни[к]))
print("")
print("--- последние 12 часов с отправками ---")
for к in sorted(часы)[-12:]:
    print("   %s  %5d" % (к, часы[к]))

# ключи конфига про паузу и окно - ищем как они реально называются
print("")
print("--- ключи конфига про отправку ---")
try:
    сырой = cfg.raw if hasattr(cfg, "raw") else None
except Exception:                                               # noqa: BLE001
    сырой = None
for к in ("sending", "schedule", "pacing", "limits", "kill_switch", "gates",
          "confirm", "provider_split"):
    з = cfg.get(к, None)
    if isinstance(з, dict) or hasattr(з, "keys"):
        print("   %-16s: %s" % (к, ", ".join(list(з.keys()))[:150]))
    elif з is not None:
        print("   %-16s: %s" % (к, str(з)[:80]))

print("")
print("--- процессы, похожие на отправщик ---")
ком = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
       "Where-Object {$_.CommandLine -like '*sender*'} | "
       "Select-Object ProcessId,CommandLine | Format-List")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                   capture_output=True, timeout=120)
т = (r.stdout or b"").decode("cp866", errors="replace")
if not т.strip():
    т = (r.stdout or b"").decode("utf-8", errors="replace")
print(т.strip()[:1500])
