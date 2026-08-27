# -*- coding: utf-8 -*-
"""Сколько времени осталось в окне и какова скорость отправки сегодня."""
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

out = subprocess.run(["powershell", "-NoProfile", "-Command",
                      "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"],
                     capture_output=True, text=True, timeout=40)
местное = (out.stdout or "").strip()
print("время сервера (Москва): %s" % местное)

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
сег = datetime.now(timezone.utc).strftime("%Y-%m-%d")
print("")
print("=== отправлено по часам (UTC / Москва = +3) ===")
всего = 0
for r in c.execute("SELECT substr(sent_at,12,2) ч, COUNT(*) n FROM messages "
                   " WHERE substr(sent_at,1,10)=? GROUP BY ч ORDER BY ч",
                   (сег,)):
    мск = (int(r["ч"]) + 3) % 24
    всего += r["n"]
    print("   %s UTC (%02d мск)  %s %d" % (r["ч"], мск, "#" * min(60, r["n"]),
                                           r["n"]))
print("   всего сегодня: %d" % всего)

ждут = c.execute("SELECT COUNT(*) FROM messages "
                 " WHERE status IN ('scheduled','sending')").fetchone()[0]
print("")
print("ждут отправки: %d" % ждут)
try:
    ч, м = [int(x) for x in местное.split()[1].split(":")[:2]]
    осталось = max(0, (14 * 60) - (ч * 60 + м))
    print("до конца окна 14:00: %d минут" % осталось)
    if всего and ч > 9:
        в_час = всего / max(1.0, (ч + м / 60.0) - 9.0)
        print("скорость сегодня: %.0f писем в час" % в_час)
        print("успеем за остаток: примерно %d писем" % (в_час * осталось / 60.0))
        print("итог: %s" % ("успеем" if в_час * осталось / 60.0 >= ждут
                            else "НЕ УСПЕЕМ, останется ~%d"
                                 % (ждут - в_час * осталось / 60.0)))
except Exception as ex:                                       # noqa: BLE001
    print("время не разобралось: %s" % ex)
c.close()
