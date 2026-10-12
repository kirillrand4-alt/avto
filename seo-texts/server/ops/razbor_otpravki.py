# -*- coding: utf-8 -*-
"""Почему автоотправщик не отправляет одобренные письма кампании 14.

1. Письма с ошибкой: какой ящик, какая ошибка, когда пробовали.
2. Ящики: SMTP-хост:порт каждого и проверка соединения ПРЯМО СЕЙЧАС.
3. Маршрутизация: какие пулы и ящики положены направлению Meyer.
4. Автоотправщик: последние попытки отправки по журналу событий.
"""
import re
import socket
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("--- письма кампании 14 в отправке ---")
for р in c.execute(
        "SELECT status, mailbox_id, COUNT(*) n, MAX(attempt_count) a, "
        "       MAX(updated_at) u, MAX(substr(COALESCE(last_error,''),1,90)) e "
        "  FROM messages WHERE campaign_id=14 AND status IN "
        "  ('scheduled','sending','claimed','failed','sent','deferred') "
        " GROUP BY status, mailbox_id"):
    print("   %-10s ящик=%-28s %3d попыток<=%s обн %s | %s"
          % (р["status"], р["mailbox_id"], р["n"], р["a"], str(р["u"])[:16], р["e"]))

print("")
print("--- ящики из конфига и соединение СЕЙЧАС ---")
ящики = cfg.get("mailboxes", []) or []
хосты = {}
for м in ящики:
    ид = getattr(м, "id", None) or (м.get("id") if isinstance(м, dict) else None)
    хост = getattr(м, "smtp_host", None) or (м.get("smtp_host") if isinstance(м, dict) else None)
    порт = getattr(м, "smtp_port", None) or (м.get("smtp_port") if isinstance(м, dict) else None)
    пул = getattr(м, "pool", None) or (м.get("pool") if isinstance(м, dict) else None)
    if хост:
        хосты.setdefault((хост, int(порт or 465)), []).append("%s[%s]" % (ид, пул))
if not хосты:
    print("   ящики через cfg.get не читаются — тип %s" % type(ящики).__name__)
for (хост, порт), кто in sorted(хосты.items()):
    t = time.time()
    try:
        s = socket.create_connection((хост, порт), timeout=10)
        s.close()
        итог = "ОК %.1f с" % (time.time() - t)
    except Exception as e:  # noqa: BLE001
        итог = "СБОЙ %.1f с: %s" % (time.time() - t, str(e)[:60])
    print("   %-30s :%-4d %-22s %s" % (хост, порт, итог, ", ".join(кто)[:70]))

print("")
print("--- маршрутизация ---")
for к in ("routing", "pools", "division_pools", "autosend"):
    try:
        print("   %-16s %s" % (к, str(cfg.get(к))[:300]))
    except Exception as e:  # noqa: BLE001
        print("   %-16s ошибка %s" % (к, e))

print("")
print("--- события отправки за 3 часа ---")
for р in c.execute(
        "SELECT event_type, COUNT(*) n, MAX(created_at) m FROM events "
        "WHERE created_at >= datetime('now','-3 hours') "
        "GROUP BY event_type ORDER BY n DESC LIMIT 12"):
    print("   %-22s %5d  последнее %s" % (р["event_type"], р["n"], str(р["m"])[:19]))
print("=== РАЗБОР ОТПРАВКИ ===")
