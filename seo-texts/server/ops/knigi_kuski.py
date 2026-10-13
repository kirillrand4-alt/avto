# -*- coding: utf-8 -*-
"""Куски книг на сервере: архивировать старые / распаковать новые .gz.

    knigi_kuski.py arhiv     — knigi2_*.json и pasp2_*.json → _ops\\arhiv-knigi-<ts>\\
    knigi_kuski.py raspak    — склеить knigi3.gz.NNN → knigi2_*.json, pasp3.gz.NNN → pasp2_*.json
"""
import glob
import gzip
import io
import json
import os
import shutil
import sys
import time
ОПС = r"C:\sender\server\ops"
if "arhiv" in sys.argv:
    куда = r"C:\sender\_ops\arhiv-knigi-%d" % int(time.time())
    os.makedirs(куда, exist_ok=True)
    n = 0
    for п in glob.glob(os.path.join(ОПС, "knigi2_*.json")) + glob.glob(os.path.join(ОПС, "pasp2_*.json")):
        shutil.move(п, os.path.join(куда, os.path.basename(п)))
        n += 1
    print("в архив %s: %d файлов" % (куда, n))
    print("=== КУСКИ: АРХИВ ===")
if "raspak" in sys.argv:
    for префикс, выход, ключ in (("knigi3.gz.", "knigi2_", "dict"), ("pasp3.gz.", "pasp2_", "list")):
        части = sorted(glob.glob(os.path.join(ОПС, префикс + "*")))
        if not части:
            print("%s: частей нет" % префикс)
            continue
        сырьё = b"".join(open(п, "rb").read() for п in части)
        д = json.loads(gzip.decompress(сырьё).decode("utf-8"))
        if ключ == "dict":
            к, а = д["компании"], д["адреса"]
            шаг = 1500
            for i in range(0, max(len(к), 1), шаг):
                кус = {"компании": к[i:i + шаг],
                       "адреса": [x for x in а if x["inn"] in {y["inn"] for y in к[i:i + шаг]}]}
                json.dump(кус, io.open(os.path.join(ОПС, "%s%02d.json" % (выход, i // шаг)), "w",
                                       encoding="utf-8"), ensure_ascii=False)
            print("knigi: компаний %d, адресов %d, кусков %d" % (len(к), len(а), (len(к) + шаг - 1) // шаг))
        else:
            шаг = 2000
            for i in range(0, len(д), шаг):
                json.dump(д[i:i + шаг], io.open(os.path.join(ОПС, "%s%02d.json" % (выход, i // шаг)), "w",
                                                encoding="utf-8"), ensure_ascii=False)
            print("pasp: паспортов %d, кусков %d" % (len(д), (len(д) + шаг - 1) // шаг))
        for п in части:
            os.remove(п)
    print("=== КУСКИ: РАСПАКОВАНЫ ===")
