# -*- coding: utf-8 -*-
"""Только чтение: кто ест процессор на сервере."""
import subprocess

пс = ["powershell", "-NoProfile", "-Command"]
зпр = (
    "$p1 = Get-Process | Select-Object Id, ProcessName, CPU;"
    " Start-Sleep -Seconds 5;"
    " $p2 = Get-Process | Select-Object Id, ProcessName, CPU, WorkingSet;"
    " $map = @{}; foreach ($x in $p1) { $map[$x.Id] = $x.CPU };"
    " $res = foreach ($y in $p2) {"
    "   $was = $map[$y.Id]; if ($was -eq $null) { $was = 0 };"
    "   $d = $y.CPU - $was;"
    "   if ($d -gt 0.1) { [pscustomobject]@{ Id=$y.Id; Name=$y.ProcessName;"
    "     Pct=[math]::Round($d/5*100); Mem=[math]::Round($y.WorkingSet/1MB) } } };"
    " $res | Sort-Object Pct -Descending | Select-Object -First 10"
    " | ForEach-Object { \"$($_.Pct)% $($_.Mem)МБ pid=$($_.Id) $($_.Name)\" }")
out = subprocess.run(пс + [зпр], capture_output=True, text=True, timeout=120)
print("=== ТОП ПО ПРОЦЕССОРУ (замер 5 секунд) ===")
print(out.stdout.strip() or "(пусто)")

зпр2 = ("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
        " | ForEach-Object { \"$($_.ProcessId)|\""
        " + $_.CommandLine.Substring(0,[Math]::Min(78,$_.CommandLine.Length)) }")
out2 = subprocess.run(пс + [зпр2], capture_output=True, text=True, timeout=60)
print("\n=== КОМАНДНЫЕ СТРОКИ PYTHON ===")
for л in (out2.stdout or "").strip().splitlines():
    print("  " + л[:96])
