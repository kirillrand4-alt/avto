# -*- coding: utf-8 -*-
"""Где панель показывает логин пользователя — чтобы заменить на ФИО везде, а не местами.

Логины (meyer1..meyer4) НЕ переименовываю: пароли уже выданы, а на логин ссылаются
company_assignment, company_state, company_comment, activity_log и hidden_item. Поэтому
добавляется отдельное поле ФИО, а логин остаётся внутренним ключом.

Что нужно найти точно, а не на память:
  1) как собирается объект user — попадёт ли в него новая колонка само;
  2) ВСЕ места вывода логина в шаблонах и в коде: если заменить в половине, продавец
     увидит себя «Пятковой» в шапке и «meyer1» в статистике, и это хуже, чем везде логин;
  3) каким SELECT-ом статистика берёт пользователей.
"""
import io
import os
import re

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-imen.txt'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


def kusok(put, obrazec, do=0, posle=24, zagolovok=''):
    t = io.open(put, encoding='utf-8', errors='replace').read().splitlines()
    for i, l in enumerate(t, 1):
        if re.search(obrazec, l):
            pishi()
            pishi('--- %s  %s:%d' % (zagolovok or obrazec, os.path.basename(put), i))
            for j in range(max(0, i - 1 - do), min(len(t), i + posle)):
                pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:170]))
            return True
    pishi('--- %s: НЕ НАЙДЕНО в %s' % (zagolovok or obrazec, os.path.basename(put)))
    return False


RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
CS = os.path.join(KOREN, 'app', 'services', 'centro_sales.py')

pishi('########## КАК СОБИРАЕТСЯ user')
kusok(RCS, r'^def current_user', posle=26, zagolovok='current_user')
kusok(CS, r'^def authenticate|verify_password\(password, row', do=12, posle=6,
      zagolovok='проверка пароля и строка users')

pishi()
pishi('########## SELECT-Ы ПО ТАБЛИЦЕ users')
for imya, put in (('routes_centro_sales.py', RCS), ('centro_sales.py', CS)):
    t = io.open(put, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'(?i)(["\'][^"\']*FROM users[^"\']*["\'])', t):
        nomer = t[:m.start()].count('\n') + 1
        pishi('   %s:%d  %s' % (imya, nomer, m.group(1)[:150]))
        svodno('SELECT из users: %s:%d' % (imya, nomer))

pishi()
pishi('########## ГДЕ ВЫВОДИТСЯ ЛОГИН: ШАБЛОНЫ')
KAT = os.path.join(KOREN, 'app', 'templates')
schet = 0
for f in sorted(os.listdir(KAT)):
    if not f.endswith('.html'):
        continue
    put = os.path.join(KAT, f)
    for i, l in enumerate(io.open(put, encoding='utf-8', errors='replace'), 1):
        if re.search(r'\{\{[^}]*\.username[^}]*\}\}|\{\{\s*username\s*\}\}|'
                     r'value="\{\{[^}]*username', l):
            schet += 1
            pishi('   %s:%d  %s' % (f, i, l.strip()[:165]))
svodno('мест вывода логина в шаблонах: %d' % schet)

pishi()
pishi('########## ГДЕ ВЫВОДИТСЯ ЛОГИН: КОД')
schet2 = 0
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith('.py'):
            continue
        put = os.path.join(kor, f)
        for i, l in enumerate(io.open(put, encoding='utf-8', errors='replace'), 1):
            if re.search(r'user\["username"\]|user\.get\("username"\)|'
                         r'\buser\[.username.\]', l):
                schet2 += 1
                pishi('   %s:%d  %s' % (os.path.relpath(put, KOREN), i, l.strip()[:160]))
svodno('упоминаний user["username"] в коде: %d' % schet2)

pishi()
pishi('########## centro_admin.html ЦЕЛИКОМ')
t = io.open(os.path.join(KAT, 'centro_admin.html'), encoding='utf-8',
            errors='replace').read()
for i, l in enumerate(t.splitlines(), 1):
    pishi('   %4d: %s' % (i, l.rstrip()[:170]))

pishi()
pishi('########## ЕСТЬ ЛИ ГОТОВЫЙ ПРИЁМ ДОЗАВЕДЕНИЯ КОЛОНОК')
kusok(CS, r'ALTER TABLE .* ADD COLUMN', do=16, posle=10,
      zagolovok='дозаведение колонок')

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
