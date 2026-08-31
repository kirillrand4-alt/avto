# -*- coding: utf-8 -*-
"""Снять карточки прогона у компаний с выручкой ниже 30 млн.

Снимаем боевой функцией store.confirm_decide(status='skipped'), не правкой
базы руками. Трогаем ТОЛЬКО письма этого прогона (номера # из свежего лога)
и только те, у кого выручка подтверждённо ниже порога: неизвестную не трогаем.
"""
import glob
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config    # noqa: E402
from sender.store import Store      # noqa: E402

ПОРОГ = 30_000_000
ПРИМЕНИТЬ = "primenit" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
выр = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL"):
    try:
        выр[str(р["inn"])] = float(р["revenue_rub"])
    except Exception:
        pass

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)
стр = io.open(логи[0], encoding="utf-8", errors="replace").read().splitlines()
ids = sorted({int(m.group(1)) for x in стр
              for m in [re.search(r"#(\d+)\s*$", x.strip())] if m})
print("прогон: %s" % os.path.basename(логи[0]))
print("карточек этого прогона: %d" % len(ids))

снять, оставить, неизвестно = [], [], []
for rid in ids:
    к = store.confirm_get(rid)
    if not к:
        continue
    if str(к.get("status")) != "pending":
        оставить.append((rid, "статус %s" % к.get("status"), None))
        continue
    inn = str(к.get("inn") or "")
    v = выр.get(inn)
    if v is None:
        неизвестно.append((rid, inn))
    elif v < ПОРОГ:
        снять.append((rid, inn, v))
    else:
        оставить.append((rid, inn, v))

print("\n=== К СНЯТИЮ (выручка < 30 млн) ===")
for rid, inn, v in снять:
    print("  #%-6s %-12s %8.1f млн" % (rid, inn, v / 1e6))
print("\n=== ОСТАВЛЯЕМ ===")
for rid, inn, v in оставить:
    print("  #%-6s %-12s %s" % (rid, inn, ("%8.1f млн" % (v / 1e6)) if v else ""))
if неизвестно:
    print("\n=== ВЫРУЧКА НЕИЗВЕСТНА (не трогаю) ===")
    for rid, inn in неизвестно:
        print("  #%-6s %s" % (rid, inn))

сделано = 0
if ПРИМЕНИТЬ:
    for rid, inn, v in снять:
        try:
            store.confirm_decide(
                rid, status="skipped",
                reason="выручка %.1f млн < 30 млн: оборудование Meyer не по бюджету" % (v / 1e6))
            сделано += 1
        except Exception as ex:
            print("  ОШИБКА на #%s: %s" % (rid, str(ex)[:90]))

print("\n=== ИТОГ ===")
print("  к снятию: %d | оставляем: %d | выручка неизвестна: %d"
      % (len(снять), len(оставить), len(неизвестно)))
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО, снято %d" % сделано if ПРИМЕНИТЬ
                       else "показ без изменений (добавь аргумент primenit)"))
