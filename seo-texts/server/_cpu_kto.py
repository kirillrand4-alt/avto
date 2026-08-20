# -*- coding: utf-8 -*-
r"""Кто именно грузит процессор: топ процессов по CPU, а не общий процент."""
import json, subprocess
out = subprocess.run(['powershell','-NoProfile','-Command',
  "$c=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors;"
  "$a=Get-Counter '\\Process(*)\\% Processor Time' -ErrorAction SilentlyContinue;"
  "$a.CounterSamples | Where-Object {$_.InstanceName -notin @('_total','idle')} | "
  "Sort-Object CookedValue -Descending | Select-Object -First 14 | "
  "%{ '{0}|{1:N1}' -f $_.InstanceName, ($_.CookedValue / $c) };"
  "'---ЯДЕР---'; $c;"
  "'---ОБЩЕЕ---';"
  "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average;"
  "'---ПАМЯТЬ---';"
  "(Get-CimInstance Win32_OperatingSystem | %{[int]($_.FreePhysicalMemory/1024)})"],
  capture_output=True, text=True, timeout=180)
print(json.dumps({'вывод': [x.strip() for x in out.stdout.splitlines() if x.strip()]},
                 ensure_ascii=False, indent=1)[:2000])
