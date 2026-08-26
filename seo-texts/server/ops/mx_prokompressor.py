# -*- coding: utf-8 -*-
"""Чей почтовик у prokompressor.ru — чтобы понимать, чей фильтр судит тест."""
import subprocess
for д in ("prokompressor.ru", "sort-inspection.ru"):
    out = subprocess.run(["nslookup", "-type=MX", д, "8.8.8.8"],
                         capture_output=True, text=True, timeout=25)
    print("=== %s ===" % д)
    for с in (out.stdout or "").splitlines():
        if "mail exchanger" in с or "MX" in с:
            print("   " + " ".join(с.split())[:120])
