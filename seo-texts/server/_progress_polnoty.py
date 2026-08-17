# -*- coding: utf-8 -*-
"""Жив ли замер и движется ли: процессорное время и возраст процесса."""
import json, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8')
PS = r'''
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
 Where-Object { $_.CommandLine -like '*polnota_sayta*' } |
 ForEach-Object {
   $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
   [ordered]@{
     pid = $_.ProcessId
     cpu_sekund = if ($p) { [math]::Round($p.TotalProcessorTime.TotalSeconds,1) } else { $null }
     pamyat_mb = if ($p) { [int]($p.WorkingSet64/1MB) } else { $null }
     zapushchen = $_.CreationDate
   }
 } | ConvertTo-Json -Compress
'''
p = subprocess.run(['powershell', '-NoProfile', '-Command', PS],
                   capture_output=True, text=True, timeout=180)
print(p.stdout.strip()[-800:] or 'процесса нет')
