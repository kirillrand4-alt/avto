# -*- coding: utf-8 -*-
"""Темп генерации «Россия 9000»: попыток/годных за последние 15/60 мин и хвост лога."""
import io
import json
import time
from datetime import datetime
сейчас = time.time()
зап = [json.loads(с) for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8") if с.strip()]
def ts(з):
    for k in ("ts", "время", "t"):
        if з.get(k):
            try:
                return datetime.fromisoformat(str(з[k])[:19]).timestamp()
            except Exception:  # noqa: BLE001
                pass
    return 0
for окно in (15, 60):
    сп = [з for з in зап if сейчас - ts(з) < окно * 60]
    print("за %d мин: записей %d, годных %d" % (окно, len(сп), sum(1 for з in сп if з.get("godno") or з.get("ok") or з.get("годно"))))
print("ключи последней записи:", sorted(зап[-1].keys())[:20] if зап else "-")
print("сейчас на сервере: %s" % time.strftime("%H:%M:%S"))
лог = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8", errors="replace").read().splitlines()
print("\n".join(л[:220] for л in лог[-14:]))
print("=== ТЕМП 9000 ===")
