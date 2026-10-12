# -*- coding: utf-8 -*-
"""Какие куски книг долетели до сервера."""
import glob
import json
import io
import os
всего_к = всего_а = 0
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi2_*.json")):
    try:
        д = json.load(io.open(п, encoding="utf-8"))
        к, а = len(д.get("компании") or []), len(д.get("адреса") or [])
    except Exception as e:  # noqa: BLE001
        к, а = -1, -1
        print("   БИТЫЙ %s: %s" % (os.path.basename(п), e))
    всего_к += max(к, 0)
    всего_а += max(а, 0)
    print("   %-18s %7.2f MB  компаний %5d адресов %5d"
          % (os.path.basename(п), os.path.getsize(п) / 1e6, к, а))
print("")
print("=== КУСКОВ НА СЕРВЕРЕ: %d, компаний %d, адресов %d ==="
      % (len(glob.glob(r"C:\sender\server\ops\knigi2_*.json")), всего_к, всего_а))
