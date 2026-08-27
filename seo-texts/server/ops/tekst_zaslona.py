# -*- coding: utf-8 -*-
import io, re
т = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8").read()
for имя in ("RECENT_CONTACT_DAYS = ", "    def _guard(", "    def _recent_contact("):
    i = т.find(имя)
    print("=" * 60)
    if i < 0:
        print("НЕ НАЙДЕНО: %r" % имя); continue
    кон = т.find("\n    def ", i + 20)
    кусок = т[i:кон if кон > 0 else i + 400]
    if имя.startswith("RECENT"):
        кусок = т[i:т.find("\n", i) + 1]
    print(кусок)
