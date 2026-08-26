# -*- coding: utf-8 -*-
import glob, io, os, time
for п in sorted(glob.glob(r"C:\sender\_ops\predprosev_meyer-*.log"), key=os.path.getmtime):
    print("%-44s %7d б  %s" % (os.path.basename(п), os.path.getsize(п),
                               time.strftime("%d.%m %H:%M:%S", time.localtime(os.path.getmtime(п)))))
ж = r"C:\sender\_ops\predprosev-meyer.jsonl"
if os.path.exists(ж):
    строк = sum(1 for _ in io.open(ж, encoding="utf-8", errors="replace"))
    print("журнал вердиктов: %d строк" % строк)
