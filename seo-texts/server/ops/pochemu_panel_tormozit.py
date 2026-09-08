# -*- coding: utf-8 -*-
"""Почему экран подтверждения грузится долго: размеры, объём, время запроса."""
import os, sys, time, urllib.request
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

БАЗА = r"C:\sender\sender.db"
for суф in ("", "-wal", "-shm"):
    п = БАЗА + суф
    try:
        print("   %-24s %10.1f МБ" % (os.path.basename(п),
                                      os.path.getsize(п) / 1048576.0))
    except OSError:
        print("   %-24s нет" % os.path.basename(п))

store = Store(БАЗА)
with store._lock:
    т0 = time.time()
    n = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'").fetchone()[0]
    т1 = time.time()
    объём = store._conn.execute(
        "SELECT SUM(LENGTH(panel_json)), AVG(LENGTH(panel_json)), "
        "       SUM(LENGTH(body)) FROM confirm_reviews "
        " WHERE status='pending'").fetchone()
    т2 = time.time()
    строки = store._conn.execute(
        "SELECT id, email, subject, body, panel_json FROM confirm_reviews "
        " WHERE status='pending' ORDER BY created_at DESC LIMIT 200").fetchall()
    т3 = time.time()
print("")
print("   pending: %d (COUNT за %.2f с)" % (n, т1 - т0))
print("   panel_json суммарно %.1f МБ, в среднем %.0f байт"
      % ((объём[0] or 0) / 1048576.0, объём[1] or 0))
print("   тела писем суммарно %.1f МБ" % ((объём[2] or 0) / 1048576.0))
print("   выборка 200 строк с панелями: %.2f с" % (т3 - т2))

# сам эндпоинт панели
for путь in ("/confirm?limit=50", "/confirm?limit=200"):
    url = "http://127.0.0.1:8091" + путь
    т = time.time()
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            тело = r.read()
        print("   GET %-22s %6.1f с, %8.1f КБ, код %s"
              % (путь, time.time() - т, len(тело) / 1024.0, r.status))
    except Exception as ex:                                     # noqa: BLE001
        print("   GET %-22s %6.1f с, ОШИБКА %s"
              % (путь, time.time() - т, str(ex)[:70]))
print("")
print("=" * 70)
print("=== ЭКРАН ПОДТВЕРЖДЕНИЯ: ЗАМЕР ===")
