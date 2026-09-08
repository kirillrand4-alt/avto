# -*- coding: utf-8 -*-
"""Хвост логов панели: что происходит прямо сейчас."""
import io, os, time
for п in (r"C:\sender\_ops\panel_out.log", r"C:\sender\_ops\panel_err.log",
          r"C:\sender\_ops\pixel.err.log"):
    print("=" * 74)
    try:
        р = os.path.getsize(п)
        with io.open(п, "rb") as f:
            f.seek(max(0, р - 4000))
            т = f.read().decode("utf-8", errors="replace")
    except OSError as ex:
        print("%s: %s" % (п, ex))
        continue
    print("%s  %.1f КБ  изменён %s"
          % (п, р / 1024.0, time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
    строки = [с for с in т.splitlines() if с.strip()][-22:]
    for с in строки:
        print("   " + с[:150])
