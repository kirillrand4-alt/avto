# -*- coding: utf-8 -*-
import glob, io, os, time
for имя, ф in (("партия 1", r"C:\sender\_ops\sud-vtoryh.jsonl"),
               ("партия 2", r"C:\sender\_ops\sud-vtoryh-2.jsonl")):
    n = 0
    try:
        n = sum(1 for _ in io.open(ф, encoding="utf-8"))
    except Exception:
        pass
    print("%s: вердиктов %d" % (имя, n))
л = sorted(glob.glob(r"C:\sender\_ops\sud_vtoryh_pisem-*.log"), key=os.path.getmtime)
if л:
    п = л[-1]
    print("лог %s (%.1f мин назад)" % (os.path.basename(п), (time.time()-os.path.getmtime(п))/60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-10:]:
        print("   " + с[:140])
