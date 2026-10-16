# -*- coding: utf-8 -*-
"""Что реально отдаёт панель: index.html, имя бандла, есть ли в нём perepiska, заголовки кэша; и статусы лидов в базе."""
import glob, os, re, sqlite3, urllib.request
for порт in (8000, 8080, 8787, 5000, 80):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:%d/" % порт, timeout=5)
        h = r.read().decode("utf-8", "replace"); break
    except Exception: continue
else:
    h = ""; порт = None
print("порт", порт, "cache-control:", r.headers.get("Cache-Control") if порт else None)
бандл = re.findall(r'assets/(index-[^"]+\.js)', h); print("index.html ссылается на:", бандл)
for b in бандл:
    try:
        js = urllib.request.urlopen("http://127.0.0.1:%d/assets/%s" % (порт, b), timeout=10).read().decode("utf-8", "replace")
        print(b, "perepiska в отдаваемом бандле:", "perepiska" in js, "| кэш:", urllib.request.urlopen("http://127.0.0.1:%d/assets/%s" % (порт, b)).headers.get("Cache-Control"))
    except Exception as e: print(b, e)
print("в dist лежит:", [os.path.basename(p) for p in glob.glob(r"C:\sender\sender\web\dist\assets\index-*.js")])
c = sqlite3.connect(r"C:\sender\sender.db")
print(c.execute("SELECT status, COUNT(*) FROM leads GROUP BY 1").fetchall())
