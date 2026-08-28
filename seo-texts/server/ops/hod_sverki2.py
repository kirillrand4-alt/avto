# -*- coding: utf-8 -*-
import glob, io, os, time
л = sorted(glob.glob(r"C:\sender\_ops\sverka_yashchikov_polnaya-*.log"),
           key=os.path.getmtime)
print("логов сверки: %d" % len(л))
if л:
    п = л[-1]
    print("=== %s (%.1f мин назад, %d байт) ===" % (os.path.basename(п),
                                                    (time.time()-os.path.getmtime(п))/60,
                                                    os.path.getsize(п)))
    ст = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for с in ст[:34]:
        print("   " + с[:150])
    о = os.path.splitext(п)[0] + ".err"
    if os.path.exists(о) and os.path.getsize(о):
        print("--- ошибки ---")
        for с in io.open(о, encoding="utf-8", errors="replace").read().splitlines()[-6:]:
            print("   " + с[:150])
print("в _ops лежит: %s"
      % os.path.exists(r"C:\sender\_ops\sverka_yashchikov_polnaya.py"))
