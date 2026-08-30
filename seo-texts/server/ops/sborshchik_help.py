# -*- coding: utf-8 -*-
import subprocess
r = subprocess.run([r"C:\seostat\Parser2\.venv\Scripts\python.exe",
                    r"scripts\daily_collect.py", "--help"],
                   cwd=r"C:\seostat\Parser2", capture_output=True, text=True,
                   timeout=120)
print("код %s" % r.returncode)
print((r.stdout or "") [:2500])
print((r.stderr or "")[:600])
