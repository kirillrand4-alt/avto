# -*- coding: utf-8 -*-
r"""fixKA (21.10): поиск пароля admin панели КЦ на сервере – только чтение.

Владелец не помнит пароль admin панели КЦ (/obzvon/centro), в переписке его не было, в базе – только bcrypt-хеш.
Скрипт собирает строки-кандидаты из настроек сервера (.env в C:\seostat, переменные службы nssm obzvon/p25obzvon в
реестре, небольшие текстовые файлы C:\seostat вне .venv и баз, код панели) и сверяет каждую с хешем admin.
Печатает ТОЛЬКО совпавший пароль и где он найден; прочие кандидаты (там могут быть чужие секреты) и сам хеш не
печатаются – только их число. Плюс имена переменных окружения, через которые код панели заводит пользователей.

    python3 zapusk_na_servere.py fixKA_admin_poisk.py
"""
import io
import os
import re
import sqlite3
import subprocess
import sys

SALES = r'C:\seostat\data\centro_sales.db'
KOREN = r'C:\seostat'
PROPUSK = {'.venv', 'node_modules', '__pycache__', '.git', '_bekap', 'drop-storage', 'data'}
RASSH = {'.env', '.txt', '.md', '.py', '.json', '.ini', '.toml', '.yaml', '.yml', '.cfg', '.bat', '.ps1', '.cmd', ''}

VENV = r'C:\seostat\.venv\Scripts\python.exe'
try:
    import bcrypt

    def sovpal(p, h):
        return bcrypt.checkpw(p.encode('utf-8'), h.encode('utf-8'))
except ImportError:
    if os.path.normcase(sys.executable) != os.path.normcase(VENV):   # bcrypt есть только в окружении панели
        r = subprocess.run([VENV, os.path.abspath(__file__)], capture_output=True, text=True, encoding='utf-8', errors='replace')
        print(r.stdout[-5000:], r.stderr[-1500:])
        raise SystemExit(r.returncode)
    from passlib.hash import bcrypt as _pb

    def sovpal(p, h):
        return _pb.verify(p, h)

s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True, timeout=30)
heshi = {u: h for u, h, in s.execute("SELECT username, password_hash FROM users")}
print('пользователи панели КЦ:', sorted(heshi))
h = heshi.get('admin')
if not h:
    raise SystemExit('нет пользователя admin')

kandidaty = {}          # строка -> где найдена (первое место)


def dobavit(znach, gde):
    znach = (znach or '').strip().strip('"\'')
    if 4 <= len(znach.encode('utf-8')) <= 72 and znach not in kandidaty:
        kandidaty[znach] = gde


KLYUCH = re.compile(r'(pass|parol|парол|pwd)', re.I)


def iz_teksta(t, gde):
    for n, stroka in enumerate(t.splitlines(), 1):
        if not KLYUCH.search(stroka):
            continue
        m = re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(.+)$', stroka)
        if m:
            dobavit(m.group(2), '%s:%d' % (gde, n))
        for tok in re.findall(r'[^\s"\'`,;:=()\[\]{}<>|]{4,64}', stroka):
            dobavit(tok, '%s:%d' % (gde, n))
        for para in re.findall(r'([A-Za-z0-9_.-]+):([^\s,"\']{4,64})', stroka):   # «логин:пароль,логин2:пароль2»
            dobavit(para[1], '%s:%d' % (gde, n))


# 1) файлы C:\seostat (кроме .venv, баз, бэкапов, дропа)
nfaylov = 0
for kor, papki, fayly in os.walk(KOREN):
    papki[:] = [p for p in papki if p not in PROPUSK and kor.count(os.sep) - KOREN.count(os.sep) < 2]
    for f in fayly:
        put = os.path.join(kor, f)
        if os.path.splitext(f)[1].lower() not in RASSH and not f.lower().startswith('.env'):
            continue
        try:
            if os.path.getsize(put) > 300000:
                continue
            iz_teksta(io.open(put, encoding='utf-8', errors='replace').read(), os.path.relpath(put, KOREN))
            nfaylov += 1
        except OSError:
            pass

# 2) переменные служб nssm (реестр)
try:
    import winreg
    for sl in ('obzvon', 'p25obzvon', 'seostat'):
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Services\%s\Parameters' % sl)
            for imya in ('AppEnvironmentExtra', 'AppEnvironment', 'AppParameters'):
                try:
                    v, _ = winreg.QueryValueEx(k, imya)
                    iz_teksta('\n'.join(v) if isinstance(v, list) else str(v), 'служба %s/%s' % (sl, imya))
                except OSError:
                    pass
        except OSError:
            pass
except ImportError:
    pass

# 3) переменные окружения этого процесса
for k, v in os.environ.items():
    if KLYUCH.search(k):
        dobavit(v, 'окружение %s' % k)

# как заводятся пользователи – код инструмента (это код, секретов в нём нет)
_cu = os.path.join(KOREN, 'app', 'tools', 'centro_users.py')
if os.path.exists(_cu):
    print('--- centro_users.py (начало) ---')
    for n, stroka in enumerate(io.open(_cu, encoding='utf-8', errors='replace'), 1):
        if n <= 45:
            print('  %2d %s' % (n, stroka.rstrip()[:110]))
print('просмотрено файлов: %d; кандидатов: %d' % (nfaylov, len(kandidaty)))

# как код панели заводит пользователей (только имена переменных и место)
for kor, papki, fayly in os.walk(os.path.join(KOREN, 'app')):
    papki[:] = [p for p in papki if p not in PROPUSK]
    for f in fayly:
        if not f.endswith('.py'):
            continue
        put = os.path.join(kor, f)
        for n, stroka in enumerate(io.open(put, encoding='utf-8', errors='replace'), 1):
            if 'upsert_user(' in stroka or re.search(r'(getenv|environ)\W.*(ADMIN|PASS|USER)', stroka, re.I):
                imena = re.findall(r'["\']([A-Z][A-Z0-9_]{3,})["\']', stroka)
                print('  код: %s:%d %s' % (os.path.relpath(put, KOREN), n, ('переменные ' + ', '.join(imena)) if imena else stroka.strip()[:90] if 'upsert_user(' in stroka and '=' not in stroka else '(строка скрыта)'))

naydeno = [(p, g) for p, g in kandidaty.items() if sovpal(p, h)]
if naydeno:
    for p, g in naydeno:
        print('СОВПАЛ пароль admin: %s  (где: %s)' % (p, g))
else:
    print('пароль admin среди кандидатов НЕ найден')
for u in sorted(heshi):
    if u != 'admin':
        nu = [g for p, g in kandidaty.items() if sovpal(p, heshi[u])]
        print('  у %s совпадений: %d%s' % (u, len(nu), (' (где: %s)' % nu[0]) if nu else ''))
