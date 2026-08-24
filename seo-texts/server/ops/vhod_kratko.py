# -*- coding: utf-8 -*-
"""Компактно: от кого работают службы, политика блокировки, RDP, замок."""
import subprocess


def _sh(cmd, t=45):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=t)
        return ((p.stdout or b"") + (p.stderr or b"")).decode("cp866", "replace")
    except Exception as e:
        return "ОШИБКА: %s" % e


def _ps(s, t=45):
    return _sh('powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"'
               % s.replace('"', '\\"'), t)


print("КТО МЫ:", _sh("whoami").strip())
print("АДМИН:", _ps("([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')").strip())

print("\n=== ОТ КОГО СЛУЖБЫ (кому сломает смена пароля) ===")
print(_ps("Get-CimInstance Win32_Service | Where-Object {$_.StartName -and $_.StartName -notmatch 'LocalSystem|LocalService|NetworkService|NT AUTHORITY|NT SERVICE'} | Select-Object Name,StartName,State | Format-Table -AutoSize | Out-String -Width 160"))

print("=== SenderPanel ===")
print(_ps("Get-CimInstance Win32_Service -Filter \\\"Name like '%ender%'\\\" | Select-Object Name,StartName,State,StartMode | Format-List | Out-String -Width 160"))

print("=== ЗАДАНИЯ ПЛАНИРОВЩИКА ОТ ИМЕНИ ПОЛЬЗОВАТЕЛЯ ===")
print(_ps("Get-ScheduledTask | ForEach-Object { $p=$_.Principal; if ($p.UserId -and $p.LogonType -eq 'Password') { '{0}  <-  {1}' -f $_.TaskName,$p.UserId } }"))

print("=== ПОЛИТИКА БЛОКИРОВКИ ===")
print(_sh("net accounts"))

print("=== ЗАМОК НА Administrator ===")
print(_ps("$u=[ADSI]'WinNT://./Administrator,User'; 'IsAccountLocked=' + $u.IsAccountLocked + '  UserFlags=' + $u.UserFlags"))

print("=== ЛОКАЛЬНЫЕ АДМИНЫ ===")
print(_ps("Get-LocalGroupMember -Group Administrators | Select-Object -ExpandProperty Name"))

print("=== RDP ===")
print("служба:", _ps("(Get-Service TermService).Status").strip())
print("порт:", _ps("(Get-ItemProperty 'HKLM:\\\\System\\\\CurrentControlSet\\\\Control\\\\Terminal Server\\\\WinStations\\\\RDP-Tcp').PortNumber").strip())
print("запрет RDP:", _ps("(Get-ItemProperty 'HKLM:\\\\System\\\\CurrentControlSet\\\\Control\\\\Terminal Server').fDenyTSConnections").strip())
