# -*- coding: utf-8 -*-
"""Кто мы на сервере, в каком состоянии учётки и RDP. Ничего не меняет."""
import subprocess, sys


def _sh(cmd, cp=None):
    for кодировка in (cp or ["cp866", "cp1251", "utf-8"]):
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
            out = (p.stdout or b"") + (p.stderr or b"")
            return out.decode(кодировка, "replace")
        except Exception as e:
            return "ОШИБКА: %s" % e
    return ""


def _ps(script):
    return _sh('powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"' % script.replace('"', '\\"'))


print("=== КТО МЫ ===")
print(_sh("whoami"))
print("--- админ? ---")
print(_ps("([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"))

print("=== ЛОКАЛЬНЫЕ УЧЁТКИ ===")
print(_ps("Get-LocalUser | Select-Object Name,Enabled,LastLogon,PasswordLastSet | Format-Table -AutoSize | Out-String -Width 200"))

print("=== ПОЛИТИКА БЛОКИРОВКИ ===")
print(_sh("net accounts"))

print("=== СОСТОЯНИЕ АДМИНОВ (блокировка) ===")
print(_ps("Get-LocalGroupMember -Group Administrators | Select-Object Name,ObjectClass | Format-Table -AutoSize | Out-String -Width 200"))
for имя in ("Administrator", "Админ", "admin"):
    от = _sh('net user "%s"' % имя)
    if "not exist" not in от.lower() and "не найден" not in от.lower() and "1000" not in от[:40]:
        print("--- net user %s ---" % имя)
        print(от[:1600])

print("=== RDP ===")
print(_ps("(Get-Service TermService).Status"))
print(_ps("(Get-ItemProperty 'HKLM:\\\\System\\\\CurrentControlSet\\\\Control\\\\Terminal Server').fDenyTSConnections"))
print(_ps("(Get-ItemProperty 'HKLM:\\\\System\\\\CurrentControlSet\\\\Control\\\\Terminal Server\\\\WinStations\\\\RDP-Tcp').PortNumber"))

print("=== НЕУДАЧНЫЕ ВХОДЫ (4625) за сутки ===")
print(_ps("$e=Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddDays(-1)} -ErrorAction SilentlyContinue; 'всего: '+($e|Measure-Object).Count"))
print(_ps("$e=Get-WinEvent -FilterHashtable @{LogName='Security';Id=4740;StartTime=(Get-Date).AddDays(-3)} -ErrorAction SilentlyContinue; $e | Select-Object -First 5 TimeCreated,Message | Format-List | Out-String -Width 200"))
