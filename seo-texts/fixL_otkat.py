# -*- coding: utf-8 -*-
r"""fixL (15.10): откат ОДНОГО сквозного теста лида в Битрикс по компании 7130001590 (meyer9).

Удаляются ТОЛЬКО строки, созданные тестом: company_state (inn, meyer9) – если до теста её не было,
company_comment / activity_log / zvonok_sobytie / bitrix_lid по этому ИНН, созданные meyer9 начиная с момента теста.
Чужие строки не трогаются. Перед удалением – копия базы продаж (C:\centro2\_bekap\fixL-otkat-<время>\) и журнал
удаляемых строк на дроп (fixL-otkat-zhurnal-<время>.json). Лид в самом Битриксе вебхук удалить не может – владелец вручную.

    python3 zapusk_na_servere.py fixL_otkat.py --do                          # строки по ИНН сейчас (до теста)
    python3 zapusk_na_servere.py fixL_otkat.py --suho --s 2026-10-15T05:20:00  # что будет удалено (UTC ISO начала теста)
    python3 zapusk_na_servere.py fixL_otkat.py --primenit --s <UTC ISO>
    python3 zapusk_na_servere.py fixL_otkat.py --proverka                    # живой код на копиях баз: «Новый», в очереди, без «уже заводили»
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
INN, LOGIN = '7130001590', 'meyer9'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')


def arg(k, d=''):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def stroki(c, s):
    out = {}
    out['company_state'] = [dict(r) for r in c.execute(
        'SELECT rowid AS _rowid, * FROM company_state WHERE inn=? AND username=? AND updated_at>=?', (INN, LOGIN, s))]
    out['company_comment'] = [dict(r) for r in c.execute(
        'SELECT * FROM company_comment WHERE inn=? AND username=? AND created_at>=?', (INN, LOGIN, s))]
    out['activity_log'] = [dict(r) for r in c.execute(
        'SELECT * FROM activity_log WHERE inn=? AND username=? AND created_at>=?', (INN, LOGIN, s))]
    out['zvonok_sobytie'] = [dict(r) for r in c.execute(
        'SELECT * FROM zvonok_sobytie WHERE inn=? AND username=? AND created_at>=?', (INN, LOGIN, s))]
    out['bitrix_lid'] = [dict(r) for r in c.execute(
        'SELECT * FROM bitrix_lid WHERE inn=? AND kto=? AND kogda>=?', (INN, LOGIN, s))]
    return out


def vse_po_inn(c):
    return {t: c.execute('SELECT COUNT(*) FROM %s WHERE inn=?' % t, (INN,)).fetchone()[0]
            for t in ('company_state', 'company_comment', 'activity_log', 'zvonok_sobytie', 'bitrix_lid')}


if '--do' in sys.argv:
    c = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
    print('строк по %s сейчас: %s' % (INN, vse_po_inn(c)))
    print('назначение:', c.execute('SELECT username FROM company_assignment WHERE inn=?', (INN,)).fetchall())
    print('UTC сейчас: %s' % time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()))
    raise SystemExit(0)

if '--suho' in sys.argv or '--primenit' in sys.argv:
    s = arg('--s')
    if len(s) < 16:
        raise SystemExit('нужен --s <UTC ISO начала теста>')
    c = sqlite3.connect(SALES, timeout=30)
    c.row_factory = sqlite3.Row
    st = stroki(c, s)
    ranshe = c.execute('SELECT COUNT(*) FROM activity_log WHERE inn=? AND created_at<?', (INN, s)).fetchone()[0]
    ranshe_kom = c.execute('SELECT COUNT(*) FROM company_comment WHERE inn=? AND created_at<?', (INN, s)).fetchone()[0]
    print('найдено строк теста: %s' % {k: len(v) for k, v in st.items()})
    print('строк по ИНН до теста: activity_log %d, company_comment %d (company_state удаляется, только если их 0)' % (ranshe, ranshe_kom))
    for k, v in st.items():
        for r in v:
            print('  %s: %s' % (k, json.dumps({x: (str(y)[:160]) for x, y in r.items()}, ensure_ascii=False)))
    plohie = [r for r in st['company_state'] if r['call_result'] != 'v_rabote']
    if plohie or ranshe:
        raise SystemExit('ОСТАНОВКА: состояние не от теста (было до теста или не «Взял в работу») – вручную')
    if '--suho' in sys.argv:
        raise SystemExit(0)
    papka = os.path.join(KOREN, '_bekap', 'fixL-otkat-' + VREMYA)
    os.makedirs(papka, exist_ok=True)
    a = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
    b = sqlite3.connect(os.path.join(papka, 'centro_sales_meyer1-do-otkata.db'))
    a.backup(b)
    b.close()
    a.close()
    zh = {'chto': 'fixL: откат сквозного теста лида в Битрикс (%s, %s), начало теста %s UTC' % (INN, LOGIN, s),
          'kogda': time.strftime('%Y-%m-%d %H:%M:%S'), 'kopiya_bazy': papka, 'udaleno': st}
    put_zh = os.path.join(DROP, 'fixL-otkat-zhurnal-%s.json' % VREMYA)
    io.open(put_zh, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=1, default=str))
    print('журнал удаляемых строк: дроп %s' % os.path.basename(put_zh))
    try:
        c.execute('BEGIN IMMEDIATE')
        n = 0
        for r in st['company_state']:
            n += c.execute('DELETE FROM company_state WHERE rowid=? AND inn=? AND username=?', (r['_rowid'], INN, LOGIN)).rowcount
        for t in ('company_comment', 'activity_log', 'zvonok_sobytie', 'bitrix_lid'):
            for r in st[t]:
                n += c.execute('DELETE FROM %s WHERE id=? AND inn=?' % t, (r['id'], INN)).rowcount
        if n != sum(len(v) for v in st.values()):
            raise RuntimeError('удалено %d, ждали %d' % (n, sum(len(v) for v in st.values())))
        ost = stroki(c, s)
        if any(ost.values()):
            raise RuntimeError('после удаления остались строки теста')
        c.commit()
        print('УДАЛЕНО строк: %d; по ИНН теперь: %s' % (n, vse_po_inn(c)))
    except Exception as e:  # noqa: BLE001
        c.rollback()
        print('ОШИБКА, транзакция отменена: %s' % e)
        raise SystemExit(5)
    raise SystemExit(0)


def proverka(kat, sales_db):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = sales_db
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[k] = kat
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    h = {'Cookie': '%s=%s' % (rcs.COOKIE, rcs._token(LOGIN, int(time.time()) + 3600))}
    plohih = 0
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro', params={'inn': INN}, headers=h, follow_redirects=False)
        g = o.status_code == 200 and 'st-metka st-new' in o.text and 'class="fixL-lid-stroka"' not in o.text
        plohih += not g
        print('%s карточка %s у %s во «Всей очереди»: %s, статус «Новый»: %s, строки о лиде нет: %s' % (
            'ОК ' if g else 'ПЛОХО', INN, LOGIN, o.status_code, 'st-metka st-new' in o.text, 'class="fixL-lid-stroka"' not in o.text))
        o = kl.get(PUT + '/centro', params={'q': INN}, headers=h, follow_redirects=False)
        g = o.status_code == 200 and ('inn=%s' % INN) in o.text
        plohih += not g
        print('%s в очереди %s (поиск по ИНН): %s' % ('ОК ' if g else 'ПЛОХО', LOGIN, o.status_code))
        o = kl.get(PUT + '/centro/bitrix-lid/dannye', params={'inn': INN}, headers=h, follow_redirects=False)
        g = o.status_code == 200 and o.json().get('lidy') == []
        plohih += not g
        print('%s окно лида: прежних лидов нет (%s)' % ('ОК ' if g else 'ПЛОХО', o.json().get('lidy') if o.status_code == 200 else o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    proverka(sys.argv[i + 1], sys.argv[i + 2])
    raise SystemExit(0)

if '--proverka' in sys.argv:
    papka = os.path.join(KOREN, '_bekap', 'fixL-otkat-proverka-' + VREMYA)
    os.makedirs(papka, exist_ok=True)
    ts, tk = os.path.join(papka, 't_sales.db'), os.path.join(papka, 't_kat.db')
    for src, dst in ((SALES, ts), (KAT, tk)):
        a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
        b = sqlite3.connect(dst)
        a.backup(b)
        b.close()
        a.close()
    r = subprocess.run([VENV, os.path.abspath(__file__), '--render', tk, ts], capture_output=True, timeout=1500, cwd=KOREN, env=SREDA)
    print(r.stdout.decode('utf-8', 'replace')[-4000:])
    if r.returncode:
        print(r.stderr.decode('utf-8', 'replace')[-2000:])
    for f in (ts, tk):
        try:
            os.remove(f)
        except OSError:
            pass
