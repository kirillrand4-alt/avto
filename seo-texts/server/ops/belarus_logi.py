# -*- coding: utf-8 -*-
import io, os
for имя in ("katalog_belarus_razobrat-0825-183316.log",
            "katalog_belarus_razobrat-0825-183813.log"):
    п = os.path.join(r"C:\sender\_ops", имя)
    print("==== %s ====" % имя)
    стр = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for с in стр[-14:]:
        print("   " + с[:170])
    print("")
