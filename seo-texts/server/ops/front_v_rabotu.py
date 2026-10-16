# -*- coding: utf-8 -*-
"""Служба SenderPanel отдаёт статику из C:\\sender\\web\\dist (--static-dir), а фронт
собирается в C:\\sender\\sender\\web\\dist. Копируем свежую сборку туда, откуда её
реально отдают. Бэкап старой — C:\\sender\\web\\dist.bak-<время>.
Откат: front_v_rabotu.py --otkat"""
import glob, os, shutil, sys, time
SRC, DST = r"C:\sender\sender\web\dist", r"C:\sender\web\dist"
if "--otkat" in sys.argv:
    б = sorted(glob.glob(DST + ".bak-*"))[-1]
    shutil.rmtree(DST); shutil.copytree(б, DST); print("откат из", б); sys.exit()
б = DST + ".bak-%d" % int(time.time())
shutil.copytree(DST, б)
shutil.rmtree(DST); shutil.copytree(SRC, DST)
print("бэкап:", б); print("теперь отдаётся:", os.listdir(os.path.join(DST, "assets")))
