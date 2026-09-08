# -*- coding: utf-8 -*-
"""Что панель увидела после перезапуска: пороги, потолок, паузы, темп."""
import subprocess, sys, time
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.auto_send import ENABLED_KEY                        # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.otkaz_spam import porogi, min_yashchikov            # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)

ком = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
       "Where-Object {$_.CommandLine -like '*serve-api*'} | "
       "Select-Object ProcessId,CreationDate | Format-List")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                   capture_output=True, timeout=120)
т = (r.stdout or b"").decode("cp866", errors="replace")
if not т.strip():
    т = (r.stdout or b"").decode("utf-8", errors="replace")
print("--- процесс панели ---")
print(т.strip()[:400])

пауз = 0
готовы = []
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    st = store.get_mailbox_state(mb.mailbox_id)
    if st is not None and getattr(st, "paused", False):
        пауз += 1
    else:
        готовы.append(mb.mailbox_id)

ушло = отказ = 0
по_часам = Counter()
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at") if c in кол), None)
    тп = next((c for c in ("type", "event_type") if c in кол), None)
    ушло = store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at >= "
        "datetime('now','start of day')").fetchone()[0]
    отказ = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE %s='reject_spam' AND %s >= "
        "datetime('now','start of day')" % (тп, вр)).fetchone()[0]
    for р in store._conn.execute(
            "SELECT sent_at FROM messages WHERE status='sent' AND sent_at >= "
            "datetime('now','-3 hours')"):
        по_часам[str(р["sent_at"]).replace("T", " ")[:13]] += 1
    ждут = store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0]

print("")
print("--- отправки по часам (UTC, 3 часа) ---")
for к in sorted(по_часам):
    print("   %s  %4d" % (к, по_часам[к]))
print("")
print("=" * 74)
print("=== ПОСЛЕ ПЕРЕЗАПУСКА ===")
print("сейчас UTC %s" % теперь.strftime("%H:%M"))
п_я, п_н = porogi(cfg)
print("пороги заслона: ящик %s, направление %s, минимум ящиков %s"
      % (п_я, п_н, min_yashchikov(cfg)))
try:
    print("автоотправка включена: %s" % store.get_setting(ENABLED_KEY, False))
    print("send_limits: %s" % store.get_setting("send_limits"))
except Exception as ex:                                         # noqa: BLE001
    print("настройки не прочитались: %s" % str(ex)[:70])
print("ящиков Meyer готовы: %d, на паузе: %d" % (len(готовы), пауз))
print("за сегодня: ушло %d, отказов %d; ждут отправки %d" % (ушло, отказ, ждут))
