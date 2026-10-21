# -*- coding: utf-8 -*-
"""Диагностика: размер бандла и сжатие ответов живой службы (только чтение)."""
import os
import re
import time
import urllib.request
d = r"C:\sender\web\dist"
html = open(os.path.join(d, "index.html"), encoding="utf-8").read()
for ref in sorted(set(re.findall(r"/assets/[A-Za-z0-9._-]+", html))):
    п = os.path.join(d, ref.lstrip("/").replace("/", os.sep))
    req = urllib.request.Request("http://127.0.0.1:8091" + ref,
                                 headers={"Accept-Encoding": "gzip, br"})
    t0 = time.perf_counter()
    r = urllib.request.urlopen(req, timeout=30)
    тело = r.read()
    print(f"{ref}: на диске {os.path.getsize(п)/1e3:.0f} КБ, отдано {len(тело)/1e3:.0f} КБ, "
          f"Content-Encoding={r.headers.get('Content-Encoding')}, "
          f"Cache-Control={r.headers.get('Cache-Control')}, {(time.perf_counter()-t0)*1000:.0f} мс")
print("=== ГОТОВО ===")
