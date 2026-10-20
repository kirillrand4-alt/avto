# -*- coding: utf-8 -*-
# 20.10: checko по списку ИНН с дропа (уникальные Meyer без выручки ни в checko, ни в ФНС) — fsa_meyer_checko.py в режиме CHECKO_VHOD.
import os, subprocess, sys
os.environ['CHECKO_VHOD'] = 'checko-vhod-meyer-unik.json'
r = subprocess.run([sys.executable, r'C:\sender\server\fsa_meyer_checko.py'], cwd=r'C:\sender\server', capture_output=True, text=True, errors='replace')
print(r.stdout[-1500:], r.stderr[-500:])
