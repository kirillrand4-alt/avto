# -*- coding: utf-8 -*-
import glob, io, os, time
n = 0
try:
    n = sum(1 for _ in io.open(r"C:\sender\_ops\spasenie-182.jsonl", encoding="utf-8"))
except Exception:
    pass
print("классифицировано компаний: %d" % n)
л = sorted(glob.glob(r"C:\sender\_ops\spasti_182-*.log"), key=os.path.getmtime)
if л:
    п = л[-1]
    print("лог %s (%.1f мин назад)" % (os.path.basename(п), (time.time()-os.path.getmtime(п))/60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-14:]:
        print("   " + с[:150])
    о = os.path.splitext(п)[0] + ".err"
    if os.path.exists(о) and os.path.getsize(о):
        print("--- ошибки ---")
        for с in io.open(о, encoding="utf-8", errors="replace").read().splitlines()[-6:]:
            print("   " + с[:150])
