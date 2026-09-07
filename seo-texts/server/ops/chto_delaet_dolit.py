# -*- coding: utf-8 -*-
"""Что делает висящий dolit_iz_zhurnala_hodilki и сколько ему осталось."""
import glob, io, os, subprocess, time
for п in sorted(glob.glob(r"C:\sender\_ops\dolit_iz_zhurnala_hodilki-*.log"))[-2:]:
    print("=" * 70)
    print("%s  %d байт  изменён %s"
          % (п, os.path.getsize(п),
             time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
    if os.path.getsize(п):
        print(io.open(п, encoding="utf-8", errors="replace").read()[-1200:])
ком = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
       "Where-Object {$_.CommandLine -like '*dolit_iz_zhurnala*'} | "
       "Select-Object ProcessId,CreationDate | Format-List")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                   capture_output=True, timeout=120)
print((r.stdout or b"").decode("cp866", errors="replace"))
