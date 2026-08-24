# -*- coding: utf-8 -*-
"""Дать владельцу вход на сервер, ничего не сломав.

Владелец не может войти вторые сутки. Причина установлена: учётку
Administrator запирает политика (10 неудачных попыток за 10 минут вешают
замок на 10 минут), а RDP открыт наружу на штатном порту и его
перебирают — в журнале 4740 чужой Caller Computer Name.

Почему НЕ сбрасываем пароль Administrator. Админский сброс через net user
рвёт DPAPI-секреты профиля: сохранённые учётки браузера и Дельфина
станут нечитаемыми, а Дельфин нам нужен — на нём решатель капч, приватные
мобильные прокси и доступ к hh. Замок сброс всё равно не снимает: через
десять минут перебор повесит его снова.

Что делаем вместо этого: снимаем замок и заводим ВТОРУЮ административную
учётку. Владелец входит сразу, профиль Administrator не тронут, а пароль
к нему он при желании сменит уже изнутри Windows — так DPAPI переживает
смену. Учётка удаляется одной командой: net user <имя> /delete.

Пароль печатается один раз в вывод задания. Он случайный, 20 знаков.
"""
import secrets
import string
import subprocess

ИМЯ = "kirill"
АЛФАВИТ = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
ПАРОЛЬ = "".join(secrets.choice(АЛФАВИТ) for _ in range(20))


def _ps(s, t=60):
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"'
           % s.replace('"', '\\"'))
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=t)
        return ((p.stdout or b"") + (p.stderr or b"")).decode("cp866",
                                                              "replace").strip()
    except Exception as e:                                     # noqa: BLE001
        return "ОШИБКА: %s" % e


def _net(*арг):
    try:
        p = subprocess.run(["net"] + list(арг), capture_output=True, timeout=60)
        return ((p.stdout or b"") + (p.stderr or b"")).decode("cp866",
                                                              "replace").strip()
    except Exception as e:                                     # noqa: BLE001
        return "ОШИБКА: %s" % e


print("=== 1. СОСТОЯНИЕ Administrator ===")
print("замок сейчас:",
      _ps("([ADSI]'WinNT://./Administrator,User').IsAccountLocked"))
print(_ps("$u=[ADSI]'WinNT://./Administrator,User'; "
          "$u.IsAccountLocked=$false; $u.SetInfo(); 'замок снят'"))
print("замок после:",
      _ps("([ADSI]'WinNT://./Administrator,User').IsAccountLocked"))
print("срабатываний замка за сутки:",
      _ps("$e=Get-WinEvent -FilterHashtable @{LogName='Security';Id=4740;"
          "StartTime=(Get-Date).AddDays(-1)} -ErrorAction SilentlyContinue; "
          "($e | Measure-Object).Count", t=90))

print("\n=== 2. ВТОРАЯ АДМИНИСТРАТИВНАЯ УЧЁТКА ===")
есть = _ps("if (Get-LocalUser -Name '%s' -ErrorAction SilentlyContinue) "
           "{'да'} else {'нет'}" % ИМЯ)
print("учётка «%s» уже была: %s" % (ИМЯ, есть))
if есть.strip().lower() == "да":
    print(_net("user", ИМЯ, ПАРОЛЬ))
else:
    print(_net("user", ИМЯ, ПАРОЛЬ, "/add",
               "/comment:Vtoraya administrativnaya uchyotka vladeltsa",
               "/expires:never"))
# группа администраторов зовётся по-разному в разных локалях — берём по SID
print(_ps("$g=(Get-LocalGroup | Where-Object {$_.SID -like 'S-1-5-32-544'})"
          ".Name; Add-LocalGroupMember -Group $g -Member '%s' "
          "-ErrorAction SilentlyContinue; 'в группе ' + $g" % ИМЯ))
print(_ps("Set-LocalUser -Name '%s' -PasswordNeverExpires $true; "
          "Enable-LocalUser -Name '%s'; 'учётка включена, пароль бессрочный'"
          % (ИМЯ, ИМЯ)))
# право входа по RDP: группа тоже локализуется, берём по SID
print(_ps("$r=(Get-LocalGroup | Where-Object {$_.SID -like '*-555'}).Name; "
          "if($r){Add-LocalGroupMember -Group $r -Member '%s' "
          "-ErrorAction SilentlyContinue; 'в группе ' + $r} "
          "else {'группы удалённого доступа нет — админам она не нужна'}" % ИМЯ))

print("\n=== 3. ПРОВЕРКА ===")
print(_ps("Get-LocalUser -Name '%s' | Select-Object Name,Enabled,"
          "PasswordExpires | Format-List | Out-String -Width 120" % ИМЯ))
print(_ps("$g=(Get-LocalGroup | Where-Object {$_.SID -like 'S-1-5-32-544'})"
          ".Name; Get-LocalGroupMember -Group $g | "
          "Select-Object -ExpandProperty Name"))

print("\n=== 4. ВХОД ===")
print("  пользователь: .\\%s" % ИМЯ)
print("  пароль:       %s" % ПАРОЛЬ)
print("  RDP по-прежнему на штатном порту 3389")
print("\nПароль сменить: net user %s <новый>" % ИМЯ)
print("Удалить учётку:  net user %s /delete" % ИМЯ)
