# -*- coding: utf-8 -*-
"""Окно для проверки доменов КЦ (владелец 16.10, вариант 1): очередь КЦ
придержать, 5 ящиков проверки снять с паузы, отправить proverka_domenov_kc.py,
вернуть паузу и прежнее время писем. Всё в одном процессе, в finally — возврат.
Журнал — _ops/proverka-domenov-okno.jsonl."""
import io
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ЯЩИКИ = ["kirchatov.n@compressor-pro-systems.ru", "v.melnikov@compressor-air-expert.ru",
         "aleksandr.dmitriev@kompressor-air-trade.ru", "dmitriev.a@kompressor-pro-expert.ru",
         "novoseltsev.p@kompressor-pro-trade.ru"]
КАМП_КЦ = (10, 15, 16, 5, 6, 1)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ж = io.open(r"C:\sender\_ops\proverka-domenov-okno.jsonl", "a", encoding="utf-8")
завтра = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")
# 1) придержать очередь КЦ
старое = c.execute("SELECT id, scheduled_at FROM messages WHERE status IN ('scheduled','approved') "
                   "AND campaign_id IN (%s)" % ",".join(map(str, КАМП_КЦ))).fetchall()
пауза = {r[0]: (r[1], r[2]) for r in c.execute(
    "SELECT mailbox_id, paused, pause_reason FROM mailbox_state WHERE mailbox_id IN (%s)"
    % ",".join("?" * len(ЯЩИКИ)), ЯЩИКИ)}
ж.write(json.dumps({"ts": time.time(), "scheduled": старое, "pauza": пауза}, ensure_ascii=False) + "\n")
ж.flush()
with c:
    c.executemany("UPDATE messages SET scheduled_at=? WHERE id=? AND status IN ('scheduled','approved')",
                  [(завтра, m) for m, _ in старое])
print("очередь КЦ придержана:", len(старое))
try:
    with c:
        for я in ЯЩИКИ:
            c.execute("UPDATE mailbox_state SET paused=0 WHERE mailbox_id=?", (я,))
    print("пауза снята с", len(ЯЩИКИ))
    р = subprocess.run([sys.executable, r"C:\sender\server\ops\proverka_domenov_kc.py", "--katit"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=840)
    print("\n".join(s for s in (р.stdout or "").splitlines() if "УШЛО" in s or "СБОЙ" in s or "ушло:" in s))
    print((р.stderr or "")[-400:])
finally:
    with c:
        for я, (p, why) in пауза.items():
            c.execute("UPDATE mailbox_state SET paused=?, pause_reason=? WHERE mailbox_id=?", (p, why, я))
        c.executemany("UPDATE messages SET scheduled_at=? WHERE id=? AND status IN ('scheduled','approved')",
                      [(sa, m) for m, sa in старое])
    print("пауза и время писем возвращены")
