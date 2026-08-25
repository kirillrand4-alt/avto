# -*- coding: utf-8 -*-
import glob, io, os, time
логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"), key=os.path.getmtime)
п = логи[-1]
print("==== %s (%.1f мин назад) ====" % (os.path.basename(п),
                                         (time.time() - os.path.getmtime(п)) / 60))
строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
print("--- начало ---")
for с in строки[:30]:
    print("   " + с[:165])
print("--- хвост ---")
for с in строки[-12:]:
    print("   " + с[:165])
