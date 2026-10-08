# -*- coding: utf-8 -*-
"""Изоляция копии от боевых баз: загрузчик, который кладёт ВЕСЬ .env в окружение процесса.

ЧТО СЛОМАНО. routes_park читает пути из os.environ под СВОИМИ именами, с боевыми путями
по умолчанию:
    SALES_DB   = CENTRO_SALES_DB        -> C:\\seostat\\data\\centro_sales.db
    CENTRO_DB  = CENTRO_DB              -> C:\\seostat\\data\\centrifugal.db
    SALES_DB_PUT = PARK_OCHERED_SALES_DB -> C:\\seostat\\data\\centro_sales.db  (ПИШЕТ)
    OCHERED_DB = PARK_OCHERED_DB        -> C:\\seostat\\data\\centrifugal.db    (ПИШЕТ)
    BAZA       = PARK_PANEL_DB          -> C:\\seostat\\data\\park_panel.db
.env копии читает только pydantic (settings), в os.environ он не попадает — значит
сервер копии на «Списке», «Парке» и в календарном блоке смотрел в боевую базу, а кнопки
«в обзвон» и «мусор» на «Парке» писали бы в неё. Замер: записей в боевой с 07.10 — ноль.

КАК ЧИНИТСЯ.
  1. В .env копии дописываются ВСЕ имена, под которыми код ищет базы, с путями копии.
  2. park_panel.db копируется в копию — иначе «Парк» остаётся единственным окном в боевую.
  3. Сервер запускается через C:\\centro2\\zapusk.py: он кладёт ВЕСЬ .env в os.environ
     (с перезаписью — глобальная переменная сервера не должна перебить путь копии) и
     ОТКАЗЫВАЕТСЯ стартовать, если хоть одна переменная *DB смотрит в C:\\seostat\\data.
  4. Проверка — в процессе, поднятом тем же загрузчиком, без load_dotenv: обходятся все
     загруженные модули app.* и ищутся строки с боевым путём.
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DATA = os.path.join(KOREN, 'data')
ENV = os.path.join(KOREN, '.env')
BOEVAYA = r'C:\seostat\data'
PORT = 8016

itog = []


def skazat(s=''):
    itog.append(str(s))
    print(s)


# ------------------------------------------------------------ 0. отпечаток боевой ДО
def otpechatok():
    p = os.path.join(BOEVAYA, 'centro_sales.db')
    b = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
    o = (os.path.getsize(p), os.path.getmtime(p),
         b.execute('select count(*) from activity_log').fetchone()[0],
         b.execute('select count(*) from company_assignment').fetchone()[0],
         b.execute('select count(*) from company_state').fetchone()[0])
    b.close()
    return o


do = otpechatok()
skazat('боевая centro_sales.db ДО: %d байт, журнал %d, назначений %d, состояний %d'
       % (do[0], do[2], do[3], do[4]))

# ------------------------------------------------------------ 1. копия park_panel.db
src = os.path.join(BOEVAYA, 'park_panel.db')
dst = os.path.join(DATA, 'park_panel.db')
if os.path.exists(src):
    if not os.path.exists(dst):
        # копируем через API резервного копирования sqlite: файл может быть открыт
        # боевым процессом, простое копирование поймало бы его на середине записи
        s = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
        d = sqlite3.connect(dst)
        s.backup(d)
        d.close()
        s.close()
        skazat('park_panel.db скопирована в копию: %.1f МБ' % (os.path.getsize(dst) / 1048576.0))
    else:
        skazat('park_panel.db в копии уже есть: %.1f МБ' % (os.path.getsize(dst) / 1048576.0))
else:
    skazat('ВНИМАНИЕ: боевой park_panel.db нет — «Парк» в копии будет пустым')

# ------------------------------------------------------------ 2. .env: все имена баз
NADO = {
    'CENTRIFUGAL_DB': os.path.join(DATA, 'centrifugal.db'),
    'CENTRO_SALES_DB': os.path.join(DATA, 'centro_sales.db'),
    'CENTRO_DB': os.path.join(DATA, 'centrifugal.db'),
    'PARK_OCHERED_SALES_DB': os.path.join(DATA, 'centro_sales.db'),
    'PARK_OCHERED_DB': os.path.join(DATA, 'centrifugal.db'),
    'PARK_PANEL_DB': dst,
    'OBZVON_ROOT_PATH': '/obzvon-meyer',
}
stroki = io.open(ENV, encoding='utf-8').read().splitlines()
uzhe = {}
for i, l in enumerate(stroki):
    if '=' in l and not l.lstrip().startswith('#'):
        uzhe[l.split('=', 1)[0].strip().upper()] = i
shutil.copy2(ENV, ENV + time.strftime('.do-izolyacii-%Y%m%d-%H%M%S'))
dobavleno = []
for k, v in NADO.items():
    if k in uzhe:
        stroki[uzhe[k]] = '%s=%s' % (k, v)
    else:
        dobavleno.append('%s=%s' % (k, v))
if dobavleno:
    stroki += ['', '# --- имена, под которыми routes_park ищет базы (у него свои, не как у',
               '# --- pydantic). Без них он брал БОЕВЫЕ пути по умолчанию.'] + dobavleno
io.open(ENV, 'w', encoding='utf-8').write('\n'.join(stroki) + '\n')
skazat('.env: переписано %d, дописано %d (%s)' % (len(NADO) - len(dobavleno), len(dobavleno),
                                                ', '.join(x.split('=')[0] for x in dobavleno)))

# ------------------------------------------------------------ 3. загрузчик
ZAPUSK = r'''# -*- coding: utf-8 -*-
"""Запуск копии панели обзвона Мейера. Только через этот файл.

Кладёт ВЕСЬ C:\centro2\.env в окружение процесса ДО импорта приложения. Без этого часть
кода (routes_park) читает пути баз из os.environ, не находит их и берёт БОЕВЫЕ пути
C:\seostat\data\... по умолчанию: копия показывала боевую базу, а кнопки «в обзвон» и
«мусор» на «Парке» писали бы в неё. Значения из .env ПЕРЕЗАПИСЫВАЮТ окружение — глобальная
переменная сервера не должна перебить путь копии.

Предохранитель: если хоть одна переменная с DB в имени смотрит в C:\seostat\data,
сервер не стартует.

    python zapusk.py             — запустить сервер
    python zapusk.py --proverka  — только загрузить окружение и приложение, показать пути
"""
import os
import sys

KOREN = os.path.dirname(os.path.abspath(__file__))
BOEVAYA = r"C:\seostat\data"


def zagruzit_env():
    for stroka in open(os.path.join(KOREN, ".env"), encoding="utf-8"):
        stroka = stroka.strip()
        if not stroka or stroka.startswith("#") or "=" not in stroka:
            continue
        k, v = stroka.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")
    chuzhie = {k: v for k, v in os.environ.items()
               if "DB" in k.upper() and BOEVAYA.lower() in v.lower()}
    if chuzhie:
        raise SystemExit("ОТКАЗ: переменные смотрят в боевые базы: %s" % chuzhie)


os.chdir(KOREN)
sys.path.insert(0, KOREN)
zagruzit_env()

if __name__ == "__main__":
    if "--proverka" in sys.argv:
        import logging
        import warnings
        warnings.filterwarnings("ignore")
        logging.disable(logging.CRITICAL)
        import app.obzvon  # noqa: F401
        from app.api import routes_park  # noqa: F401
        boevye = []
        for imya, mod in list(sys.modules.items()):
            if not imya.startswith("app") or mod is None:
                continue
            for atr, v in list(vars(mod).items()):
                if isinstance(v, str) and BOEVAYA.lower() in v.lower():
                    boevye.append("%s.%s = %s" % (imya, atr, v))
        for imya in ("SALES_DB", "CENTRO_DB", "SALES_DB_PUT", "OCHERED_DB", "BAZA"):
            print("routes_park.%-13s = %s" % (imya, getattr(routes_park, imya, "-")))
        print("модульных строк с боевым путём: %d" % len(boevye))
        for s in boevye:
            print("   " + s)
        raise SystemExit(0)
    import uvicorn
    uvicorn.run("app.obzvon:app", host="127.0.0.1",
                port=int(os.environ.get("CENTRO2_PORT", "8016")))
'''
io.open(os.path.join(KOREN, 'zapusk.py'), 'w', encoding='utf-8').write(ZAPUSK)
io.open(os.path.join(KOREN, 'start-centro2.bat'), 'w', encoding='utf-8').write(
    '@echo off\r\n'
    'rem Копия панели обзвона Мейера, порт %d. Запуск ТОЛЬКО через zapusk.py:\r\n'
    'rem он кладёт весь .env в окружение, иначе часть кода берёт боевые базы.\r\n'
    'cd /d %s\r\n'
    '"%s" zapusk.py\r\n' % (PORT, KOREN, VENV))
skazat('записаны zapusk.py и start-centro2.bat')

# ------------------------------------------------------------ 4. проверка загрузчиком
r = subprocess.run([VENV, os.path.join(KOREN, 'zapusk.py'), '--proverka'],
                   capture_output=True, timeout=600, cwd=KOREN,
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
skazat('')
skazat('--- что видит приложение, поднятое загрузчиком (без load_dotenv)')
for l in (r.stdout + r.stderr).decode('utf-8', 'replace').strip().splitlines()[-14:]:
    skazat('   ' + l)

# ------------------------------------------------------------ 5. перезапуск через загрузчик
# Только если загрузчик прошёл проверку: иначе предохранитель не даст серверу стартовать,
# и я положу панель вместо того, чтобы её починить.
vyvod = (r.stdout + r.stderr).decode('utf-8', 'replace')
if r.returncode != 0 or 'ОТКАЗ' in vyvod:
    skazat('')
    skazat('ЗАГРУЗЧИК ПРОВЕРКУ НЕ ПРОШЁЛ (rc=%s) — сервер НЕ перезапускаю, работает прежний'
           % r.returncode)
    print('\n===== ИТОГ =====')
    for s in itog:
        print(s)
    raise SystemExit(1)
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск через zapusk.py (изоляция баз) %s =====\n'
         % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
time.sleep(9)
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
slushaet = [l.split()[-1] for l in p.stdout.decode('cp866', 'replace').splitlines()
            if (':%d ' % PORT) in l and 'LISTENING' in l.upper()]
skazat('')
skazat('порт %d слушает: %s' % (PORT, slushaet or 'НИКТО — смотри centro2.log'))

posle = otpechatok()
skazat('боевая centro_sales.db ПОСЛЕ: %d байт, журнал %d, назначений %d, состояний %d — %s'
       % (posle[0], posle[2], posle[3], posle[4],
          'не изменилась' if posle == do else 'ИЗМЕНИЛАСЬ'))

print()
print('===== ИТОГ =====')
for s in itog:
    print(s)
