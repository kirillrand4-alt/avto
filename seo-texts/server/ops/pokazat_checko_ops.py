# -*- coding: utf-8 -*-
import io, sys
for п in (r"C:\sender\server\ops\checko_contacts.py",
          r"C:\sender\server\ops\zalit_rekvizity.py"):
    стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
    print("=" * 74)
    print("### %s — %d строк" % (п, len(стр)))
    print("=" * 74)
    for i, с in enumerate(стр[:52]):
        print("%4d| %s" % (i + 1, с[:110]))
