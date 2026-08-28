# -*- coding: utf-8 -*-
import glob, io, os, time
for имя, путь in (("постановка", r"C:\sender\_ops\vtorye_adresa_2-*.log"),
                  ("генерация",  r"C:\sender\_ops\partiya_gen-*.log")):
    л = sorted(glob.glob(путь), key=os.path.getmtime)
    if not л:
        print("%s: логов нет" % имя); continue
    п = л[-1]
    print("=== %s: %s (%.1f мин назад) ===" % (имя, os.path.basename(п),
                                               (time.time()-os.path.getmtime(п))/60))
    for с in io.open(п, encoding="utf-8", errors="replace").read().splitlines()[-9:]:
        print("   " + с[:140])
n = 0
try:
    n = sum(1 for _ in io.open(r"C:\sender\_ops\vtorye-adresa-2.jsonl", encoding="utf-8"))
except Exception:
    pass
print("во второй партии поставлено: %d" % n)
