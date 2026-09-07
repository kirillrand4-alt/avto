# -*- coding: utf-8 -*-
import glob, io, os
for п in sorted(glob.glob(r"C:\sender\_ops\zalit_agro_v_bazu-*.*")):
    р = os.path.getsize(п)
    print("=" * 70)
    print("%s  %d байт  %s" % (п, р, os.path.getmtime(п)))
    if р:
        print(io.open(п, encoding="utf-8", errors="replace").read()[-2500:])
