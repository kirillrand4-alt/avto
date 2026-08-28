# -*- coding: utf-8 -*-
import io, re
т = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8").read()
print("строк: %d" % т.count("\n"))
i = т.find("уже писали")
while i > 0:
    н = т.rfind("\n    def ", 0, i)
    print("=" * 60)
    print(т[max(0, i - 1800):i + 400])
    break
