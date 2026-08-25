# -*- coding: utf-8 -*-
"""Из какого каталога панель отдаёт статику — коротко и по делу."""
import io
import os
import re
import subprocess
import time

for п in (r"C:\sender\web\dist\index.html",
          r"C:\sender\sender\web\dist\index.html"):
    if not os.path.exists(п):
        print("%s — НЕТ" % п)
        continue
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print("%s\n   изменён %s" % (п, time.strftime(
        "%d.%m %H:%M", time.localtime(os.path.getmtime(п)))))
    for с in re.findall(r'(?:src|href)="([^"]+)"', т):
        print("   -> %s" % с)
    активы = os.path.join(os.path.dirname(п), "assets")
    if os.path.isdir(активы):
        for ф in sorted(os.listdir(активы))[:6]:
            print("      assets/%s  %s" % (ф, time.strftime(
                "%d.%m %H:%M", time.localtime(
                    os.path.getmtime(os.path.join(активы, ф))))))

print("\n=== ПАРАМЕТРЫ СЛУЖБЫ (nssm) ===")
for ключ in ("AppDirectory", "Application", "AppParameters"):
    try:
        в = subprocess.run(["nssm", "get", "SenderPanel", ключ],
                           capture_output=True, timeout=20)
        з = (в.stdout or b"").decode("utf-16-le", "replace").strip("\x00 \r\n")
        if not з:
            з = (в.stdout or b"").decode("utf-8", "replace").strip()
        print("   %-14s %s" % (ключ, з[:160]))
    except Exception as e:  # noqa: BLE001
        print("   %-14s не прочитан: %s" % (ключ, str(e)[:50]))
