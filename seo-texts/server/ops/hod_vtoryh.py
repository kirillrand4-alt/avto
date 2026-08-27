# -*- coding: utf-8 -*-
import glob, io, os, time
л = sorted(glob.glob(r"C:\sender\_ops\vtorye_adresa_v_ochered-*.log"), key=os.path.getmtime)
if л:
    п = л[-1]
    print("лог %s (%.1f мин назад)" % (os.path.basename(п), (time.time()-os.path.getmtime(п))/60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-12:]:
        print("   " + с[:150])
    о = os.path.splitext(п)[0] + ".err"
    if os.path.exists(о) and os.path.getsize(о):
        print("--- ошибки ---")
        for с in io.open(о, encoding="utf-8", errors="replace").read().splitlines()[-6:]:
            print("   " + с[:150])
сл = r"C:\sender\_ops\vtorye-adresa.jsonl"
print("в следе адресов: %d" % sum(1 for _ in io.open(сл, encoding="utf-8")))
