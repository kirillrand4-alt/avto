# -*- coding: utf-8 -*-
"""Панель на новом коде? Смотрим, что она отвечает через свой HTTP, а не файл."""
import io, json, os, sqlite3, subprocess, sys, time
т = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8").read()
print("на диске: заслон по адресу+потолок компании: %s"
      % ("ЕСТЬ" if "COMPANY_CONTACTS_PER_PERIOD" in т else "НЕТ"))
л = io.open(r"C:\sender\sender\ai_letter.py", encoding="utf-8").read()
print("на диске: линза покупателя: %s" % ("ЕСТЬ" if "ВЗГЛЯД ТРЕТИЙ" in л else "НЕТ"))
# когда служба стартовала
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Name python* | Sort-Object StartTime -Descending | "
         "Select-Object -First 4 Id,StartTime,@{n='cmd';e={$_.Path}} | "
         "ConvertTo-Json -Compress)"],
        capture_output=True, text=True, timeout=40)
    print("процессы python: %s" % (out.stdout or out.stderr)[:400])
except Exception as e:
    print("процессы не посмотрел: %s" % str(e)[:80])
