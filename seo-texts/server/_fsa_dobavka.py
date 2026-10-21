# -*- coding: utf-8 -*-
# 21.10, владелец: (1) опт в сегментах Meyer «оставляем такие»; (2) перепрогон спорных — бывшие «нет» стали Meyer/КЦ;
# (3) Цербер «делай» — производства из реестра Цербера, которых не было в базе деклараций. Все — та же бесплатная схема, что у
# всей базы: checko заново (кандидат в сайт), «ИНН на сайте» по кандидатам (декларация / домен почты / checko; без xmlriver;
# справочники и страницы-списки отсеиваются), подтверждённые -> конвейер с паспортом. Наборы: fsavo (Meyer), fsavok (КЦ),
# cerb (Meyer, Цербер). Ждёт текущий проход checko по всей базе (прокси общие). Durable — как у _fsa_noch.
import io, json, os, subprocess, sys, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_dobavka_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_dobavka.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-500:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_noch as N  # noqa: E402

НАБОРЫ = (('fsavo', 'meyer'), ('fsavok', 'kc'), ('cerb', 'meyer'))
сп = {}
for н, _ in НАБОРЫ:
    сп.update(json.load(io.open(os.path.join(ДРОП, н + '-spisok.json'), encoding='utf-8'))['компании'])
V.п('добавка: компаний', len(сп), '| жду проход checko по всей базе')
time.sleep(5)
while V.идёт('fsa_meyer_checko.py'):
    time.sleep(180)
порядок = sorted(сп, key=lambda i: -(сп[i].get('выручка') or 0))
with open(os.path.join(ДРОП, 'fsadob-inn.json'), 'w', encoding='utf-8') as f:
    json.dump(порядок, f)
pr, лог = V.запуск('fsa_meyer_checko.py', dict(os.environ, CHECKO_VHOD='fsadob-inn.json', CHECKO_ZANOVO='1', PYTHONIOENCODING='utf-8'),
                   'fsadob_checko')
pr.wait()
time.sleep(60)
while V.идёт('fsa_meyer_checko.py'):
    time.sleep(120)
чк = {}
for s in io.open(os.path.join(DIR, 'fsa-meyer-checko.jsonl'), encoding='utf-8', errors='replace'):
    try:
        y = json.loads(s)
    except ValueError:
        continue
    if y.get('inn') and y.get('итог') == 'ok':
        чк[y['inn']] = y
V.п('добавка: checko готов, кандидатов в сайт', sum(1 for i in порядок if (чк.get(i) or {}).get('сайт_кандидат')))
for н, цель in НАБОРЫ:
    нн, k = N.проход_базы(н, чк)
    if k:
        N.конвейер(нн, цель)
V.п('ДОБАВКА: ГОТОВО')
