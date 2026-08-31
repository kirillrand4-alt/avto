# -*- coding: utf-8 -*-
"""Какой моделью писались письма в последних прогонах и с какой отдачей."""
import glob
import io
import os
import re
import time

for п in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
                key=os.path.getmtime, reverse=True)[:6]:
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    модель = ""
    параметры = ""
    for x in с[:25]:
        if re.search(r"(?i)модель письма|модель:|письма пишет|opus|sonnet", x):
            модель = модель or x.strip()[:110]
        if re.search(r"(?i)потолок|кандидат|к генерации|отбор", x):
            параметры = параметры or x.strip()[:110]
    итог = [x for x in с if x.strip().startswith("итог:")]
    print("%-34s %5.1f ч   %s" % (os.path.basename(п),
                                  (time.time() - os.path.getmtime(п)) / 3600,
                                  (итог[-1].strip()[:80] if итог else "без итога")))
    if модель:
        print("      модель: %s" % модель)
    if параметры:
        print("      отбор:  %s" % параметры)
