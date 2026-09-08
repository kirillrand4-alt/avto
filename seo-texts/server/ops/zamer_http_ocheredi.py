# -*- coding: utf-8 -*-
"""Настоящий HTTP-замер экрана очереди: сколько длится запрос браузера.

Токен берём из хранилища панели, а не из воздуха: тот же, каким ходит сам
интерфейс. В вывод он не попадает.
"""
import json, sys, time, urllib.request
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
токен = None
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(sessions)")]
    поле = next((c for c in кол if "token" in c.lower()), None)
    if поле:
        р = store._conn.execute(
            "SELECT %s FROM sessions ORDER BY rowid DESC LIMIT 1" % поле).fetchone()
        if р and р[0]:
            токен = str(р[0])
            print("токен взят из sessions.%s (в вывод не печатается)" % поле)
    if токен is None:
        print("колонки sessions: %s" % ", ".join(кол))
if not токен:
    print("токен не нашёлся — таблицы: %s" % ", ".join(имена)[:300])
    raise SystemExit(0)

for путь in ("/api/confirm/queue?limit=1", "/api/confirm/queue?limit=50",
             "/api/confirm/groups"):
    url = "http://127.0.0.1:8091" + путь
    зап = urllib.request.Request(url, headers={"Authorization": "Bearer " + токен})
    т = time.time()
    try:
        with urllib.request.urlopen(зап, timeout=180) as r:
            тело = r.read()
        print("   %-34s %7.2f с  %9.1f КБ  код %s"
              % (путь, time.time() - т, len(тело) / 1024.0, r.status))
    except Exception as ex:                                     # noqa: BLE001
        print("   %-34s %7.2f с  ОШИБКА %s"
              % (путь, time.time() - т, str(ex)[:60]))
print("")
print("=" * 70)
print("=== HTTP-ЗАМЕР ЭКРАНА ОЧЕРЕДИ ===")
