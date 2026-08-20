# -*- coding: utf-8 -*-
r"""Перезапустить цикл фактов, чтобы он взял 32 потока и busy_timeout."""
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); os.chdir(DIR)
import storozh as S  # noqa: E402
out = subprocess.run(['powershell','-NoProfile','-Command',
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
  "Where-Object {$_.CommandLine -like '*fakty_cikl*'} | "
  "%{ Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
  capture_output=True, text=True, timeout=90)
итог = {'погашено': [x.strip() for x in out.stdout.split() if x.strip()]}
time.sleep(4)
итог['сторож'] = S.обход()
time.sleep(15)
итог['крутится'] = bool(S._крутится(S._живые(), 'fakty_cikl.py'))
итог['среда'] = {k: v for k, v in S._sreda_faktov().items() if 'KEY' not in k}
print(json.dumps(итог, ensure_ascii=False, indent=1))
