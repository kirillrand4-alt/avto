# -*- coding: utf-8 -*-
"""Кто и когда менял окно отправки — по журналу действий панели."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
print("окно сейчас:", store.get_setting("sending_window"))
print("лимиты сейчас:", str(store.get_setting("send_limits"))[:200])

with store._lock:
    try:
        ряд = store._conn.execute(
            "SELECT created_at, action, actor_user_id, detail_json FROM audit "
            "WHERE action LIKE '%window%' OR action LIKE '%limit%' "
            "OR action LIKE '%auto_send%' ORDER BY id DESC LIMIT 20").fetchall()
    except Exception as ex:                                      # noqa: BLE001
        ряд = []
        print("audit:", str(ex)[:120])
for ts, действие, кто, детали in ряд:
    print(f"  {str(ts)[:19]}  {действие:<24} кто={кто}  {str(детали)[:120]}")
