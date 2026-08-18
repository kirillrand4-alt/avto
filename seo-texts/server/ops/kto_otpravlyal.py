# -*- coding: utf-8 -*-
"""Кто на сервере вообще шлёт письма: процессы и запланированные задачи.

Панель — не единственный кандидат. Если отправку делал отдельный процесс
(задача планировщика, оркестратор), то перезапуск панели ничего не менял, и
искать надо его.
"""
import subprocess


def _ps(команда, таймаут=120):
    p = subprocess.run(["powershell", "-NoProfile", "-Command", команда],
                       capture_output=True, text=True, timeout=таймаут,
                       errors="replace")
    return ((p.stdout or "") + (p.stderr or "")).strip()


print("=== процессы python с командной строкой")
print(_ps("Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
          "Select-Object ProcessId,CreationDate,"
          "@{n='CmdLine';e={$_.CommandLine}} | Format-List")[:3000])

print("\n=== службы, похожие на наши")
print(_ps("Get-Service | Where-Object {$_.Name -match 'sender|rusprom|panel|"
          "runner'} | Select-Object Name,Status,StartType | Format-Table -Auto")[:1200])

print("\n=== задачи планировщика с нашими словами")
print(_ps("Get-ScheduledTask | Where-Object {$_.TaskName -match "
          "'sender|otprav|inbox|probe|rusprom|panel|mail'} | "
          "Select-Object TaskName,State | Format-Table -Auto")[:2000])
