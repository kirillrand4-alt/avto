# -*- coding: utf-8 -*-
"""Копия файла панели на дроп (для чтения, ничего не меняет):
    fayl_na_drop.py <имя в C:\\sender\\sender>"""
import os
import sys

import requests

п = r"C:\sender\sender\%s" % sys.argv[1]
r = requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/panel-" + sys.argv[1],
                 data=open(п, "rb").read(), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=120)
print(r.status_code, os.path.getsize(п))
