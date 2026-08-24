# -*- coding: utf-8 -*-
"""Снять замок с учётки Administrator на сервере владельца.

Причина «неверного пароля» — не пароль, а замок: политика вешает учётку на
10 минут после 10 неудачных попыток, а RDP на штатном порту перебирают
снаружи (в журнале 4740 виден чужой Caller Computer Name). Пароль тут НЕ
меняем: смена пароля админом рвёт DPAPI-секреты профиля и сохранённые
учётки служб, а замок она всё равно не снимет — через десять минут
повторится.

Скрипт только снимает замок и показывает, от чьего имени работают службы
(чтобы понимать цену возможной смены пароля). Ничего не отключает.
"""
import subprocess


def _ps(s, t=60):
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"'
           % s.replace('"', '\\"'))
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=t)
        return ((p.stdout or b"") + (p.stderr or b"")).decode("cp866", "replace").strip()
    except Exception as e:
        return "ОШИБКА: %s" % e


print("=== СЛУЖБЫ ОТ ИМЕНИ ПОЛЬЗОВАТЕЛЯ (кого задела бы смена пароля) ===")
print(_ps("$s=Get-CimInstance Win32_Service | Where-Object {$_.StartName -and "
          "$_.StartName -notmatch 'LocalSystem|LocalService|NetworkService|NT AUTHORITY|NT SERVICE'}; "
          "if($s){$s | ForEach-Object {$_.Name + ' <- ' + $_.StartName}} "
          "else {'нет таких — все от системных учёток'}"))
print("панель:", _ps("$p=Get-CimInstance Win32_Service | Where-Object {$_.Name -match 'ender'}; "
                     "if($p){$p | ForEach-Object {$_.Name+' | '+$_.StartName+' | '+$_.State}} "
                     "else {'службы с ender в имени нет'}"))

print("\n=== ЗАМОК НА Administrator ===")
print("было:", _ps("([ADSI]'WinNT://./Administrator,User').IsAccountLocked"))
print(_ps("$u=[ADSI]'WinNT://./Administrator,User'; $u.IsAccountLocked=$false; "
          "$u.SetInfo(); 'замок снят'"))
print("стало:", _ps("([ADSI]'WinNT://./Administrator,User').IsAccountLocked"))

print("\n=== СКОЛЬКО РАЗ ВЕШАЛИ ЗАМОК ЗА НЕДЕЛЮ ===")
print(_ps("$e=Get-WinEvent -FilterHashtable @{LogName='Security';Id=4740;"
          "StartTime=(Get-Date).AddDays(-7)} -ErrorAction SilentlyContinue; "
          "'срабатываний замка: ' + ($e | Measure-Object).Count", t=90))
