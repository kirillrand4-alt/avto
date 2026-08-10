# -*- coding: utf-8 -*-
"""Разбираюсь в состоянии службы обзвона, прежде чем её трогать.

Служба числится Paused, но порт 8012 отвечает 200: значит процесс жив и панель работает.
Останавливать её ради «красивого статуса», пока владелец за ней сидит, — плохая мена.
Сначала СМОТРИМ: что говорит sc, какой процесс слушает порт, что в журнале nssm.
"""
import json, re, subprocess

def ps(cmd, t=90):
    r = subprocess.run(['powershell', '-Command', cmd], capture_output=True, text=True, timeout=t)
    return (r.stdout or r.stderr).strip()

o = {}
o['sc_query'] = ps("sc.exe query obzvon | Out-String")[:400]
o['kto_slushaet_8012'] = ps(
    "Get-NetTCPConnection -LocalPort 8012 -State Listen -ErrorAction SilentlyContinue | "
    "ForEach-Object { $p=Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; "
    "\"$($_.OwningProcess) $($p.ProcessName) старт $($p.StartTime)\" }")[:300]
o['nssm_status'] = ps("& 'C:\\nssm\\nssm.exe' status obzvon 2>&1 | Out-String")[:200]
o['sluzhba_avtozapusk'] = ps(
    "(Get-CimInstance Win32_Service -Filter \"Name='obzvon'\").StartMode")[:60]
print(json.dumps(o, ensure_ascii=False, indent=1))
