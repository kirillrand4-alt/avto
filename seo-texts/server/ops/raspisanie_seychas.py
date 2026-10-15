# -*- coding: utf-8 -*-
"""Почему ждут: сколько scheduled уже наступило/впереди, по часам; последние отправки; окно автоотправки."""
import sqlite3
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сейчас = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
print("сейчас UTC", сейчас)
print("наступило:", c.execute("SELECT count(*) FROM messages WHERE status='scheduled' AND scheduled_at<=?", (сейчас,)).fetchone()[0],
      "впереди:", c.execute("SELECT count(*) FROM messages WHERE status='scheduled' AND scheduled_at>?", (сейчас,)).fetchone()[0])
print("по часам (UTC):", c.execute("SELECT substr(scheduled_at,1,13), count(*) FROM messages WHERE status='scheduled' "
      "GROUP BY 1 ORDER BY 1 LIMIT 30").fetchall())
print("отправлено за последние 30 мин:", c.execute("SELECT count(*) FROM messages WHERE status='sent' AND sent_at>=datetime('now','-30 minutes')").fetchone()[0],
      "последняя:", c.execute("SELECT max(sent_at) FROM messages WHERE status='sent'").fetchone()[0])
st = Store(r"C:\sender\sender.db")
for к in ("auto_send", "send_window", "auto_send_window"):
    try:
        print(к, st.get_setting(к))
    except Exception as е:  # noqa: BLE001
        print(к, "—", е)
print("=== РАСПИСАНИЕ СЕЙЧАС ===")
