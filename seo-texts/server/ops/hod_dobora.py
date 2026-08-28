# -*- coding: utf-8 -*-
import glob, io, os, time
л = sorted(glob.glob(r"C:\sender\_ops\dobor_vhodyashchih-*.log"), key=os.path.getmtime)
if not л:
    print("логов нет")
else:
    п = л[-1]
    print("=== %s (%.1f мин назад) ===" % (os.path.basename(п),
                                           (time.time()-os.path.getmtime(п))/60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-24:]:
        print("   " + с[:150])
    о = os.path.splitext(п)[0] + ".err"
    if os.path.exists(о) and os.path.getsize(о):
        print("--- ошибки ---")
        for с in io.open(о, encoding="utf-8", errors="replace").read().splitlines()[-8:]:
            print("   " + с[:150])
