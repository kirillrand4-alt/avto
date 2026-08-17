# -*- coding: utf-8 -*-
"""Сколько Defender реально съел процессорного времени и что у него исключено."""
import json
import subprocess
import sys

PS = r'''
$p = Get-Process MsMpEng -ErrorAction SilentlyContinue
$os = Get-CimInstance Win32_OperatingSystem
$upt = (New-TimeSpan -Start $os.LastBootUpTime -End (Get-Date)).TotalHours
$st = try { Get-MpComputerStatus } catch { $null }
$pr = try { Get-MpPreference } catch { $null }
[ordered]@{
  cpu_chasov_defender = if ($p) { [math]::Round($p.TotalProcessorTime.TotalHours, 2) } else { $null }
  pamyat_mb = if ($p) { [int]($p.WorkingSet64/1MB) } else { $null }
  uptime_chasov = [math]::Round($upt, 1)
  yader = $env:NUMBER_OF_PROCESSORS
  zashchita_v_realnom_vremeni = if ($st) { $st.RealTimeProtectionEnabled } else { 'не спросить' }
  antivirus_vklyuchen = if ($st) { $st.AntivirusEnabled } else { 'не спросить' }
  isklyucheniya_papki = if ($pr) { @($pr.ExclusionPath) } else { @() }
  isklyucheniya_processy = if ($pr) { @($pr.ExclusionProcess) } else { @() }
} | ConvertTo-Json -Depth 3 -Compress
'''
p = subprocess.run(['powershell', '-NoProfile', '-Command', PS],
                   capture_output=True, text=True, timeout=180)
т = p.stdout.strip()
i = т.find('{')
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(json.loads(т[i:]) if i >= 0 else {'сырое': т[-400:], 'ошибка': p.stderr[-300:]},
                 ensure_ascii=False, indent=1))
