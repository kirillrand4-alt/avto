# -*- coding: utf-8 -*-
"""Где определены заходы письма и как их список попадает в промпт."""
import io
import os
import re

for П in (r"C:\sender\sender\ai_letter.py", r"C:\sender\sender\ai_quota.py"):
    if not os.path.exists(П):
        continue
    т = io.open(П, encoding="utf-8", errors="replace").read()
    print("=" * 76)
    print("### %s" % os.path.basename(П))
    for м in re.finditer(r"^.{0,90}(ЗАХОД|заход).{0,110}$", т, re.M):
        с = м.group(0).strip()
        if с and not с.lstrip().startswith("#"):
            print("   %5d| %s" % (т[:м.start()].count("\n") + 1, с[:140]))
    # блок со списком заходов
    for имя in ("ЗАХОДЫ", "_ZAHODY", "ЗАХОД_СПИСОК"):
        i = т.find("%s = " % имя)
        if i >= 0:
            print("")
            print("   --- %s ---" % имя)
            print("   " + т[i:i + 1800].replace("\n", "\n   ")[:1800])
            break
