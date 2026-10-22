# -*- coding: utf-8 -*-
r"""fixKF (22.10): панель КЦ – скрыть 5 компаний, у которых блок «Оборудование – что уже известно» пуст.

Владелец: «убери компании, где нет оборудования, которое отображается; по задумке тут должно быть только то, что говорит о
факте использования ЦК воздушного». Из вариантов (5 пустых / +9 с газом / все 241 без факта про воздух) выбрано «только 5
с пустым блоком» (fixKF_razvedka.py). Скрытие – как кнопка «убрать предприятие»: hidden_item kind=company с причиной и
автором admin, возвращается ссылкой «скрытых предприятий» у админа. Код и каталог не меняются.

    python3 zapusk_na_servere.py fixKF_skryt.py --suho
    python3 zapusk_na_servere.py fixKF_skryt.py --primenit
    python3 zapusk_na_servere.py fixKF_skryt.py --otkat
Откат (--otkat): удалить эти 5 строк hidden_item (по ИНН и причине).
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import time

KOREN = r'C:\seostat'
VENV = r'C:\seostat\.venv\Scripts\python.exe'
DATA = os.path.join(KOREN, 'data')
SALES = os.path.join(DATA, 'centro_sales.db')
ZAMOK = os.path.join(KOREN, '_zamok.txt')
DROP = r'C:\seostat\drop\drop-storage'
T = time.strftime('%Y%m%d-%H%M%S')
INN = ('2504000885', '4707020432', '7701288541', '6673092454', '6319033379')
PRICHINA = 'нет фактов о воздушном ЦК: блок «Оборудование» пуст (владелец, 22.10)'
log = []


def p(*a):
    s = ' '.join(str(x) for x in a)
    log.append(s)
    print(s, flush=True)


if len(sys.argv) > 1 and sys.argv[1] == '--vnutri':
    # проверка на снимках: компания видна, в каталоге, показанных фактов 0
    sys.path.insert(0, KOREN)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    companies = {c['inn']: c for c in rcs._source_companies()[0]}
    hidden = sales.hidden_companies()
    s = sqlite3.connect('file:%s?mode=ro' % os.environ['CENTRO_SALES_DB'], uri=True)
    skr = {(str(a), str(b)) for a, b in s.execute("SELECT inn, value FROM hidden_item WHERE kind='fact'")}
    plokh = 0
    for inn in INN:
        c = companies.get(inn)
        f = (catalog.facts(inn) or rcs._fallback_fact(c)) if c else []
        pokaz = [x for x in f if not x.get('rejected') and (inn, str(x.get('id') or '')) not in skr]
        ok = c is not None and inn not in hidden and not pokaz
        plokh += not ok
        print('%s %s: в каталоге %s, скрыта %s, показанных фактов %d, всего фактов %d' % (
            'ОК ' if ok else 'ПЛОХО', inn, c is not None, inn in hidden, len(pokaz), len(f)))
    raise SystemExit(1 if plokh else 0)


def proverit() -> bool:
    stage = os.path.join(KOREN, '_stage', 'fixKF-' + T)
    os.makedirs(stage, exist_ok=True)
    try:
        puti = {}
        for imya in ('centro_sales.db', 'centrifugal.db'):
            a = sqlite3.connect('file:%s?mode=ro' % os.path.join(DATA, imya), uri=True, timeout=30)
            b = sqlite3.connect(os.path.join(stage, imya))
            a.backup(b)
            b.close()
            a.close()
            puti[imya] = os.path.join(stage, imya)
        env = {x: v for x, v in os.environ.items() if not x.startswith(('CENTRO', 'PARK_', 'OBZVON', 'CENTRIFUGAL'))}
        env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=KOREN, OBZVON_ROOT_PATH='/obzvon',
                   CENTRO_SALES_DB=puti['centro_sales.db'], CENTRIFUGAL_DB=puti['centrifugal.db'], CENTRO_DB=puti['centrifugal.db'],
                   PARK_OCHERED_SALES_DB=puti['centro_sales.db'], PARK_OCHERED_DB=puti['centrifugal.db'],
                   PARK_PANEL_DB=os.path.join(stage, 'net-park.db'), CENTRO_SESSION_SECRET='x' * 40)
        r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'], cwd=KOREN, env=env, capture_output=True, timeout=900)
        p(r.stdout.decode('utf-8', 'replace').strip())
        if r.returncode and r.returncode != 1:
            p(r.stderr.decode('utf-8', 'replace')[-2000:])
        return r.returncode == 0
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else '--suho'
    p('fixKF %s, %s' % (rezhim, T))
    if rezhim == '--suho':
        p('проверка:', 'ОК' if proverit() else 'НЕ ПРОШЛА')
        p('сухой прогон: база не трогалась')
        return
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('fixKF (скрыть 5 компаний без фактов) %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
    os.close(fd)
    try:
        s = sqlite3.connect(SALES, timeout=30)
        if rezhim == '--otkat':
            n = s.execute('DELETE FROM hidden_item WHERE kind=\'company\' AND reason=? AND inn IN (%s)' % ','.join('?' * len(INN)),
                          (PRICHINA,) + INN).rowcount
            s.commit()
            p('возвращено в панель: %d' % n)
            return
        if not proverit():
            p('ПРОВЕРКА НЕ ПРОШЛА – база не трогалась')
            raise SystemExit(1)
        bekap = os.path.join(KOREN, '_bekap', 'fixKF-' + T)
        os.makedirs(bekap, exist_ok=True)
        b = sqlite3.connect(os.path.join(bekap, 'centro_sales.db'))
        s.backup(b)
        b.close()
        p('копия базы продаж ->', bekap)
        sejchas = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())
        n = 0
        for inn in INN:     # INSERT OR IGNORE: чужое скрытие этой компании (если вдруг появилось) не перезаписывается
            n += s.execute('INSERT OR IGNORE INTO hidden_item (inn, kind, value, reason, username, created_at) VALUES (?,?,?,?,?,?)',
                           (inn, 'company', inn, PRICHINA, 'admin', sejchas)).rowcount
        s.commit()
        p('скрыто компаний: %d из %d; всего скрыто целиком теперь: %d' % (
            n, len(INN), s.execute("SELECT COUNT(DISTINCT inn) FROM hidden_item WHERE kind='company'").fetchone()[0]))
        p('ГОТОВО')
    finally:
        os.remove(ZAMOK)
        io.open(os.path.join(DROP, 'fixKF-%s-%s.txt' % (rezhim.strip('-'), T)), 'w', encoding='utf-8').write('\n'.join(log))


if __name__ == '__main__':
    main()
