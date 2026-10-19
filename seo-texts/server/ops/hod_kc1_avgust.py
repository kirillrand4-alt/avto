# -*- coding: utf-8 -*-
"""Ход генерации «КЦ-1 август»: хвост лога, итоги журнала, последние N писем.
    hod_kc1_avgust.py [N=0]"""
import io
import json
import os
import sys
from collections import Counter

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
Л = r"C:\sender\_ops\gen-kc1-avgust.log"
Ж = r"C:\sender\_ops\gen-kc1-avgust.jsonl"
try:
    pid = int(io.open(r"C:\sender\_ops\gen-kc1-avgust.pid").read())
    import subprocess
    жив = str(pid) in subprocess.run(["tasklist", "/FI", "PID eq %d" % pid], capture_output=True, text=True).stdout
except Exception:  # noqa: BLE001
    pid, жив = None, None
print("pid", pid, "жив:", жив)
т = io.open(Л, encoding="utf-8", errors="replace").read() if os.path.exists(Л) else ""
print("\n".join(т.splitlines()[-12:]))
итоги = []
if os.path.exists(Ж):
    for s in io.open(Ж, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if z.get("этап") == "итог":
            итоги.append(z)
ок = [z for z in итоги if z.get("ок")]
print("\nитогов: %d, годных: %d, потрачено $%.2f" % (len(итоги), len(ок), sum(float(z.get("цена_$") or 0) for z in итоги)))
print("брак:", Counter((z.get("брак") or ["?"])[0][:70] for z in итоги if not z.get("ок")).most_common(6))
for z in ок[-N:] if N else []:
    print("\n==== %s | #%s\nТема: %s\n\n%s" % (z.get("имя"), z.get("review_id"), z.get("тема"), z.get("тело")))
