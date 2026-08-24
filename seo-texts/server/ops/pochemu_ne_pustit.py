# -*- coding: utf-8 -*-
"""Почему не пускает под Administrator: учётки, пароль, RDP.

Панель показывала «новый пароль» при смене шаблона загрузки, но тот пароль
относится к среде восстановления (root в rescue), а не к самой Windows.
Пароль Windows живёт в SAM на диске, и загрузка рескью его не меняет.
Смотрим факты: какие учётки есть, когда последний раз менялся пароль,
не заблокирована ли учётка и слушает ли вообще RDP.
"""
import subprocess

def пс(команда):
    из = subprocess.run(["powershell", "-NoProfile", "-Command", команда],
                        capture_output=True, text=True, timeout=90)
    return (из.stdout or из.stderr).strip()

print("=== локальные учётки ===")
print(пс("Get-LocalUser | Select-Object Name,Enabled,PasswordLastSet,"
         "PasswordExpires,LastLogon | Format-Table -AutoSize | Out-String -Width 200"))

print("=== состояние Administrator ===")
print(пс("net user Administrator | Select-String "
         "'Учетная запись активна|Account active|Срок|expires|Последний вход|"
         "Last logon|Блокировка|locked'"))

print("=== RDP ===")
print(пс("(Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\"
         "Terminal Server').fDenyTSConnections"))
print("0 = RDP разрешён, 1 = запрещён")
print(пс("Get-Service TermService | Select-Object Name,Status,StartType | "
         "Format-Table -AutoSize | Out-String"))
print(пс("Get-NetTCPConnection -State Listen -LocalPort 3389 -ErrorAction "
         "SilentlyContinue | Select-Object LocalAddress,LocalPort | "
         "Format-Table -AutoSize | Out-String"))

print("=== профиль сети и правило файрвола для RDP ===")
print(пс("Get-NetConnectionProfile | Select-Object InterfaceAlias,"
         "NetworkCategory | Format-Table -AutoSize | Out-String"))
print(пс("Get-NetFirewallRule -DisplayGroup '*Remote Desktop*' -ErrorAction "
         "SilentlyContinue | Select-Object DisplayName,Enabled,Profile | "
         "Format-Table -AutoSize | Out-String -Width 160"))

print("=== неудачные входы за сутки (4625) ===")
print(пс("Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;"
         "StartTime=(Get-Date).AddDays(-1)} -MaxEvents 5 -ErrorAction "
         "SilentlyContinue | Select-Object TimeCreated,@{n='Кто';e={"
         "$_.Properties[5].Value}} | Format-Table -AutoSize | Out-String"))
