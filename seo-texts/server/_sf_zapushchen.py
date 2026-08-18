# -*- coding: utf-8 -*-
"""Запущен ли ScreamingFrog / java с его проектом — перед удалением данных."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
                    "'ScreamingFrog|screamingfrog' -or $_.Name -match 'ScreamingFrog' } | "
                    'Select-Object -ExpandProperty Name'],
                   capture_output=True, text=True, timeout=180)
имена = [x.strip() for x in (p.stdout or '').splitlines() if x.strip()]
print(json.dumps({'процессы_SF': имена or 'нет — можно удалять'},
                 ensure_ascii=False))
