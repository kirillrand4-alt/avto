# -*- coding: utf-8 -*-
import glob, io, os, time
логи = sorted(glob.glob(r"C:\sender\_ops\proverit_yashchiki-*.log"),
              key=os.path.getmtime)
if not логи:
    print("логов ещё нет")
else:
    п = логи[-1]
    print("==== %s (%.1f мин назад) ====" % (os.path.basename(п),
                                             (time.time() - os.path.getmtime(п)) / 60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-45:]:
        print("   " + с[:170])
    оши = os.path.splitext(п)[0] + ".err"
    if os.path.exists(оши) and os.path.getsize(оши):
        print("--- ошибки ---")
        for с in io.open(оши, encoding="utf-8", errors="replace").read().splitlines()[-8:]:
            print("   " + с[:170])
