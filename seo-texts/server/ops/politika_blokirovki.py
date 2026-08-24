# -*- coding: utf-8 -*-
"""Политика блокировки и кто ломился: сама ли разблокируется учётка.

Administrator заблокирован. Надо знать: на сколько минут блокировка, после
скольких промахов срабатывает и кто эти промахи делал - владелец или боты
из интернета (RDP открыт наружу, а среди неудачных входов уже мелькает
чужое имя IVANOV).
"""
import subprocess

def пс(к):
    из = subprocess.run(["powershell", "-NoProfile", "-Command", к],
                        capture_output=True, text=True, timeout=90)
    return (из.stdout or из.stderr).strip()

print("=== политика паролей и блокировки ===")
print(пс("net accounts"))

print("\n=== неудачные входы за сутки: кто и откуда ===")
print(пс("$ev = Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;"
         "StartTime=(Get-Date).AddDays(-1)} -ErrorAction SilentlyContinue; "
         "'всего промахов: ' + $ev.Count; "
         "$ev | Group-Object @{e={$_.Properties[19].Value}} | "
         "Sort-Object Count -Descending | Select-Object -First 8 Count,Name | "
         "Format-Table -AutoSize | Out-String -Width 120"))

print("=== по именам, под которыми ломились ===")
print(пс("Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;"
         "StartTime=(Get-Date).AddDays(-1)} -ErrorAction SilentlyContinue | "
         "Group-Object @{e={$_.Properties[5].Value}} | Sort-Object Count "
         "-Descending | Select-Object -First 10 Count,Name | Format-Table "
         "-AutoSize | Out-String -Width 120"))

print("=== когда учётку заблокировали (4740) ===")
print(пс("Get-WinEvent -FilterHashtable @{LogName='Security';Id=4740;"
         "StartTime=(Get-Date).AddDays(-2)} -MaxEvents 5 -ErrorAction "
         "SilentlyContinue | Select-Object TimeCreated | Format-Table "
         "-AutoSize | Out-String"))
