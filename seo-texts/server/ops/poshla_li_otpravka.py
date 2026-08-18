# -*- coding: utf-8 -*-
"""Пошла ли отправка: время старта службы + последние письма."""
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)


def _мин(ts) -> str:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return f"{(сейчас - d).total_seconds() / 60:.0f} мин назад"
    except Exception:                                            # noqa: BLE001
        return "?"


try:
    o = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Id (Get-WmiObject Win32_Service -Filter "
         "\"Name='SenderPanel'\").ProcessId).StartTime.ToString('o')"],
        capture_output=True, text=True, timeout=60, errors="replace")
    print("служба стартовала:", (o.stdout or o.stderr).strip()[:40])
except Exception as ex:                                          # noqa: BLE001
    print("старт службы не спросить:", str(ex)[:80])
print(f"сейчас {сейчас.strftime('%H:%M:%S')} UTC\n")

with store._lock:
    посл = store._conn.execute(
        "SELECT event_ts, mailbox_id FROM events WHERE event_type='sent' "
        "ORDER BY event_ts DESC LIMIT 8").fetchall()
    очередь = store._conn.execute(
        "SELECT status, COUNT(*) FROM messages WHERE status IN "
        "('scheduled','sending','failed') GROUP BY status").fetchall()
    сегодня = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='sent' "
        "AND substr(event_ts,1,10)=?", (сейчас.strftime("%Y-%m-%d"),)
    ).fetchone()[0]

print("последние отправки:")
for ts, mb in посл:
    print(f"  {str(ts)[:19]}  {str(mb):<40} {_мин(ts)}")
print(f"\nотправлено сегодня: {сегодня}")
print("очередь:", {с: n for с, n in очередь})
