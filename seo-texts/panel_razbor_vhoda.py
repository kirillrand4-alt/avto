# -*- coding: utf-8 -*-
"""Как устроен вход в панель: два слоя, схема users и чем хешируются пароли.

Три вопроса, на которые нужен точный ответ, а не догадка:
  1) какие пути сторожит BasicAuthASGI (OBZVON_USERS), а какие — куки-логин продавца;
     если страницы Мейера под обоими, новым людям понадобится и обзвонный пароль тоже;
  2) схема таблицы users: какие колонки обязательны, что лежит в поле пароля;
  3) ЧЕМ хешируется пароль. Если выдумать формат хеша, аккаунты создадутся, выглядеть
     будут нормально, и войти в них будет нельзя — поэтому беру функцию самой панели.
"""
import io
import os
import re
import sqlite3
import sys

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-vhoda.txt'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


# ---------------------------------------------------------------- 1. слои авторизации
pishi('########## BasicAuthASGI: КАКИЕ ПУТИ ОСВОБОЖДЕНЫ')
p = os.path.join(KOREN, 'app', 'obzvon.py')
stroki = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
nach = None
for i, l in enumerate(stroki, 1):
    if 'class BasicAuthASGI' in l:
        nach = i
if nach:
    for i, l in enumerate(stroki, 1):
        if nach - 14 <= i <= nach + 60:
            pishi('   %4d: %s' % (i, l.rstrip()[:170]))
else:
    pishi('   класс BasicAuthASGI не найден')
tekst = '\n'.join(stroki)
osvob = re.findall(r'(?:startswith|endswith|==|in)\s*\(?\s*["\']([^"\']*centro[^"\']*)["\']',
                   tekst)
svodno('в obzvon.py упоминаются как освобождённые/особые: %s'
       % (', '.join(sorted(set(osvob))[:8]) or 'ничего с centro'))

# ---------------------------------------------------------------- 2. схема users
pishi()
pishi('########## ТАБЛИЦА users В КОПИИ')
BAZA = os.path.join(KOREN, 'data', 'centro_sales.db')
c = sqlite3.connect(BAZA)
c.row_factory = sqlite3.Row
kol = list(c.execute('PRAGMA table_info(users)'))
for r in kol:
    pishi('   %-18s %-10s notnull=%s default=%s pk=%s'
          % (r['name'], r['type'], r['notnull'], r['dflt_value'], r['pk']))
svodno('колонки users: %s' % ', '.join(r['name'] for r in kol))
ddl = c.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
pishi('   DDL: %s' % re.sub(r'\s+', ' ', ddl)[:300])

pishi()
pishi('--- кто сейчас в копии (значение пароля НЕ печатаю, только его вид)')
for r in c.execute('SELECT * FROM users ORDER BY username'):
    d = dict(r)
    pole = next((k for k in d if 'pass' in k.lower() or 'hash' in k.lower()), None)
    znach = str(d.get(pole) or '')
    pishi('   %-12s роль %-8s активен %-3s %s: длина %d, начало %r'
          % (d.get('username'), d.get('role'), d.get('is_active'), pole,
             len(znach), znach[:7]))
svodno('пользователей в копии: %d'
       % c.execute('SELECT COUNT(*) FROM users').fetchone()[0])

# ---------------------------------------------------------------- 3. чем хешируется
pishi()
pishi('########## ФУНКЦИИ ПАРОЛЯ В КОДЕ ПАНЕЛИ')
nashlos = []
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith('.py'):
            continue
        q = os.path.join(kor, f)
        t = io.open(q, encoding='utf-8', errors='replace').read()
        for i, l in enumerate(t.splitlines(), 1):
            if re.search(r'bcrypt|hashpw|gensalt|checkpw|passlib|CryptContext|'
                         r'def .*parol|def .*password|password_hash|verify_pass', l):
                nashlos.append('%s:%d  %s' % (os.path.relpath(q, KOREN), i,
                                              l.strip()[:150]))
for s in nashlos:
    pishi('   %s' % s)
svodno('строк про хеширование: %d' % len(nashlos))

# есть ли готовая функция создания пользователя
pishi()
pishi('########## ГОТОВЫЕ ФУНКЦИИ СОЗДАНИЯ/СМЕНЫ ПОЛЬЗОВАТЕЛЯ')
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith('.py'):
            continue
        q = os.path.join(kor, f)
        t = io.open(q, encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'^def (\w*(?:user|parol|password|login)\w*)\(([^)]*)\)',
                             t, re.M | re.I):
            pishi('   %s: def %s(%s)' % (os.path.relpath(q, KOREN), m.group(1),
                                         re.sub(r'\s+', ' ', m.group(2))[:110]))
            svodno('функция: %s.%s' % (os.path.basename(q), m.group(1)))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
