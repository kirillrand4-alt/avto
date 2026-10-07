# -*- coding: utf-8 -*-
"""Копия панели обзвона: отдельный корень, свой порт, свои базы, свой .env.

ЗАЧЕМ ОТДЕЛЬНЫЙ КОРЕНЬ, А НЕ ВТОРОЙ UVICORN НА ТОМ ЖЕ КОДЕ.
На 8014 уже крутится второй экземпляр того же `app.obzvon` с тем же `.env` и той же
базой — это запасной воркер, а не копия. Владельцу нужна копия, у которой БУДЕТ ДРУГАЯ
БАЗА и в которой появится админская статистика. Если править живой код, правка приедет
и в боевую панель на 8012, а продавцы работают там прямо сейчас. Поэтому копия живёт
своим каталогом и ничего в C:\\seostat не меняет.

ЧТО КОПИРУЕТСЯ
  app\\            весь пакет (без __pycache__ и без .bak — их там сотни)
  data\\           centrifugal.db и centro_sales.db, чтобы копия завелась сразу;
                   владелец пришлёт свою базу позже, подменяется одной переменной
  .env             берётся с боевого и правится: свои пути к базам и свой DATABASE_URL

ЧТО НЕ ДЕЛАЕТСЯ БЕЗ ОТДЕЛЬНОГО РАЗРЕШЕНИЯ
  не трогается nginx: наружу копию не публикую, она слушает 127.0.0.1;
  не трогается боевой .env и боевой каталог;
  пароли и токены не печатаются — только имена переменных.
"""
import io
import os
import re
import shutil
import sys

ISTOK = r'C:\seostat'
KOREN = r'C:\centro2'
PORT = 8016
PROBA = '--proba' in sys.argv          # посчитать и ничего не делать

PROPUSK = re.compile(r'__pycache__|\.bak|\.pyc$|pered-otkatom|\.git', re.I)
# Скриншоты-доказательства: 12 114 PNG на 1 308 МБ из 1 310 МБ всего каталога app.
# Копировать их бессмысленно — они неизменяемые и нужны обеим панелям одинаково.
# Вместо копии ставится junction на оригинал: место не тратится, картинки видны.
DOKAZ_OTN = os.path.join('static', 'centro', 'dokaz')


def nuzhen(put):
    if PROPUSK.search(put):
        return False
    return DOKAZ_OTN not in put


def schitat(src):
    fajlov = bajt = propushcheno = 0
    for koren, kat, fajly in os.walk(src):
        kat[:] = [d for d in kat if nuzhen(d)]
        for f in fajly:
            p = os.path.join(koren, f)
            if nuzhen(p):
                fajlov += 1
                try:
                    bajt += os.path.getsize(p)
                except OSError:
                    pass
            else:
                propushcheno += 1
    return fajlov, bajt, propushcheno


def kopirovat(src, dst):
    skopirovano = 0
    for koren, kat, fajly in os.walk(src):
        kat[:] = [d for d in kat if nuzhen(d)]
        otn = os.path.relpath(koren, src)
        cel = dst if otn == '.' else os.path.join(dst, otn)
        os.makedirs(cel, exist_ok=True)
        for f in fajly:
            p = os.path.join(koren, f)
            if not nuzhen(p):
                continue
            shutil.copy2(p, os.path.join(cel, f))
            skopirovano += 1
    return skopirovano


print('########## ЗАМЕР ДО КОПИРОВАНИЯ')
f1, b1, pr1 = schitat(os.path.join(ISTOK, 'app'))
print('  app\\      файлов %d, %.1f МБ, пропущено мусорных %d' % (f1, b1 / 1048576.0, pr1))
for imya in ('centrifugal.db', 'centro_sales.db'):
    p = os.path.join(ISTOK, 'data', imya)
    print('  data\\%-18s %s' % (imya, ('%.1f МБ' % (os.path.getsize(p) / 1048576.0))
                                if os.path.exists(p) else 'НЕТ'))
if PROBA:
    print('\nпроба: ничего не меняла')
    raise SystemExit(0)

print('\n########## КОПИРОВАНИЕ')
if os.path.exists(KOREN):
    print('  каталог %s уже есть — НЕ трогаю, выхожу' % KOREN)
    raise SystemExit(1)
os.makedirs(os.path.join(KOREN, 'data'), exist_ok=True)
n = kopirovat(os.path.join(ISTOK, 'app'), os.path.join(KOREN, 'app'))
print('  app: скопировано файлов %d (скриншоты-доказательства не копировались)' % n)

# --- junction на каталог доказательств
import subprocess
src_dokaz = os.path.join(ISTOK, 'app', DOKAZ_OTN)
dst_dokaz = os.path.join(KOREN, 'app', DOKAZ_OTN)
os.makedirs(os.path.dirname(dst_dokaz), exist_ok=True)
if os.path.isdir(src_dokaz):
    r = subprocess.run(['cmd', '/c', 'mklink', '/J', dst_dokaz, src_dokaz],
                       capture_output=True, timeout=60)
    vyhod = (r.stdout + r.stderr).decode('cp866', 'replace').strip()
    if os.path.isdir(dst_dokaz):
        print('  junction на доказательства: %s' % vyhod[:90])
    else:
        print('  ВНИМАНИЕ: junction НЕ создан (%s). Картинки-доказательства в копии'
              ' показываться не будут, остальное работает.' % vyhod[:70])
else:
    print('  каталог доказательств не найден, пропускаю')
for imya in ('centrifugal.db', 'centro_sales.db'):
    src = os.path.join(ISTOK, 'data', imya)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(KOREN, 'data', imya))
        print('  data\\%s скопирована' % imya)

print('\n########## .env КОПИИ')
src_env = os.path.join(ISTOK, '.env')
stroki, bylo = [], set()
if os.path.exists(src_env):
    for l in io.open(src_env, encoding='utf-8', errors='replace'):
        m = re.match(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*=', l)
        if m:
            bylo.add(m.group(1).upper())
        stroki.append(l.rstrip('\n'))
NOVOE = {
    'CENTRIFUGAL_DB': os.path.join(KOREN, 'data', 'centrifugal.db'),
    'CENTRO_SALES_DB': os.path.join(KOREN, 'data', 'centro_sales.db'),
    'DATABASE_URL': 'sqlite:///./data/seo.db',
}
out = ['# .env КОПИИ панели. Отличается от боевого только путями к базам.',
       '# Боевой C:\\seostat\\.env не менялся.']
for l in stroki:
    m = re.match(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*=', l)
    if m and m.group(1).upper() in NOVOE:
        continue                      # эти перепишем ниже своими значениями
    out.append(l)
out.append('')
out.append('# --- пути к базам КОПИИ (подменить на присланную базу = поменять строку)')
for k, v in NOVOE.items():
    out.append('%s=%s' % (k, v))
io.open(os.path.join(KOREN, '.env'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('  записан %s' % os.path.join(KOREN, '.env'))
print('  переменных из боевого перенесено: %d' % len(bylo))
print('  переопределено: %s' % ', '.join(NOVOE))

print('\n########## ЗАПУСКАЛКА')
bat = os.path.join(KOREN, 'start-centro2.bat')
io.open(bat, 'w', encoding='utf-8').write(
    '@echo off\r\n'
    'rem Копия панели обзвона. Боевая на 8012, эта на %d.\r\n'
    'cd /d %s\r\n'
    '"C:\\Program Files\\Python311\\python.exe" -m uvicorn app.obzvon:app '
    '--host 127.0.0.1 --port %d\r\n' % (PORT, KOREN, PORT))
print('  записан %s' % bat)
print('\nГОТОВО. Копия: %s, порт %d. Боевая панель не тронута.' % (KOREN, PORT))
