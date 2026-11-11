# -*- coding: utf-8 -*-
"""Ручной отсев сомнительных из подтверждённых строгой проверкой (владелец 11.11: «бегло просмотри сам, сомнительных
убери»). Дописывает в gaz-kc-sud.jsonl запись ok=false по каждому ИНН (последняя запись главнее), fsync.
    gaz_ruchnoy_otsev.py ИНН,ИНН,... "причина\""""
import io, json, os, sys
from datetime import datetime, timezone
ИНН = [x.strip() for x in sys.argv[1].split(",") if x.strip()]
ПРИЧ = sys.argv[2] if len(sys.argv) > 2 else "ручной отсев"
п = r"C:\sender\_ops\gaz-kc-sud.jsonl"
посл = {}
for с in io.open(п, encoding="utf-8"):
    try: з = json.loads(с); посл[з["inn"]] = з
    except ValueError: pass
n = 0
with io.open(п, "a", encoding="utf-8") as ф:
    for и in ИНН:
        б = посл.get(и)
        if not б: print("нет в журнале:", и); continue
        ф.write(json.dumps({"inn": и, "ok": False, "konk": False, "model_ok": False, "pochemu": ПРИЧ, "f": "", "beda": "",
                            "otr": б.get("otr", ""), "gaz": б.get("gaz", ""), "model": "ручной", "ruchnoy": True,
                            "ts": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False) + "\n"); n += 1
    ф.flush(); os.fsync(ф.fileno())
print("отсеяно вручную: %d из %d" % (n, len(ИНН)))
