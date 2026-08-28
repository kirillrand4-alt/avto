# -*- coding: utf-8 -*-
import glob, io, os, time
n = 0
try:
    n = sum(1 for _ in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8"))
except Exception:
    pass
print("вердиктов в следе: %d" % n)
л = sorted(glob.glob(r"C:\sender\_ops\sud_vtoryh_pisem-*.log"), key=os.path.getmtime)
if л:
    п = л[-1]
    print("лог %s (%.1f мин назад)" % (os.path.basename(п), (time.time()-os.path.getmtime(п))/60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-8:]:
        print("   " + с[:140])
