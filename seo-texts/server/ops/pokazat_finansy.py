# -*- coding: utf-8 -*-
import io
for п in (r"C:\sender\server\ops\checko_finansy.py",
          r"C:\sender\server\ops\checko_contacts.py"):
    стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
    print("=" * 74)
    print("### %s (%d строк)" % (п.split("\\")[-1], len(стр)))
    for i, с in enumerate(стр[:46]):
        print("%4d| %s" % (i + 1, с[:112]))
