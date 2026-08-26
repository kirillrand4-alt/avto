# -*- coding: utf-8 -*-
"""Ждать, пока просев допишет строку с раскладкой, и показать хвост."""
import glob, io, os, sys, time
ЖДАТЬ = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
край = time.time() + ЖДАТЬ
логи = sorted(glob.glob(r"C:\sender\_ops\predprosev_meyer-*.log"), key=os.path.getmtime)
п = логи[-1]
while time.time() < край:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    if "раскладка просева" in т or "вхолостую" in т:
        break
    time.sleep(15)
т = io.open(п, encoding="utf-8", errors="replace").read()
for с in т.splitlines()[-30:]:
    print("   " + с[:170])
оши = os.path.splitext(п)[0] + ".err"
if os.path.exists(оши) and os.path.getsize(оши):
    print("--- ошибки ---")
    for с in io.open(оши, encoding="utf-8", errors="replace").read().splitlines()[-6:]:
        print("   " + с[:170])
