# -*- coding: utf-8 -*-
import io, os
for п, n in ((r"C:\sender\server\park_checko_sbor.py", 46),
             (r"C:\sender\_ops\checko_contacts.py", 40)):
    if not os.path.exists(п):
        print("нет %s" % п)
        continue
    стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
    print("=" * 74)
    print("### %s (%d строк)" % (п.replace("C:\\", ""), len(стр)))
    for i in range(min(n, len(стр))):
        print("%4d| %s" % (i + 1, стр[i][:112]))
