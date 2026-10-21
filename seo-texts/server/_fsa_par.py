# -*- coding: utf-8 -*-
# 21.10, владелец: «всё что можно идёт с оптимальной скоростью?» — нет: _fsa_noch (вся база: fsavm -> fsavk) и _fsa_dobavka
# (fsavo -> fsavok -> cerb) шли наборами по очереди, хотя наборы не зависят друг от друга. Здесь — все пять параллельно:
# «ИНН на сайте» (бесплатно, свои потоки у каждого набора) сразу, конвейеры (обход, доизвлечение, роли, аудит, опровергатели,
# паспорт) — не больше двух одновременно (обход — 4 процесса × 32 потока на набор; больше — рвутся TLS к шлюзу/сайтам), от
# меньшего набора к большему. Резюм: проверенные ИНН и сделанные шаги пропускаются.
import io, json, os, subprocess, sys, threading, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_par_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_par.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(40)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_noch as N  # noqa: E402

НАБОРЫ = (('cerb', 'meyer'), ('fsavok', 'kc'), ('fsavo', 'meyer'), ('fsavk', 'kc'), ('fsavm', 'meyer'))
чк = {}
for s in io.open(os.path.join(DIR, 'fsa-meyer-checko.jsonl'), encoding='utf-8', errors='replace'):
    try:
        y = json.loads(s)
    except ValueError:
        continue
    if y.get('inn') and y.get('итог') == 'ok':
        чк[y['inn']] = y
КОНВЕЙЕРОВ = threading.Semaphore(2)


def набор(н, цель):
    нн, k = N.проход_базы(н, чк)
    if not k:
        return
    with КОНВЕЙЕРОВ:
        V.п(нн, 'конвейер: компаний', k)
        N.конвейер(нн, цель)


тт = [threading.Thread(target=набор, args=x) for x in НАБОРЫ]
for т in тт:
    т.start()
for т in тт:
    т.join()
V.п('ПАРАЛЛЕЛЬНО: ГОТОВО')
