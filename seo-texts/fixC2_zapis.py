# -*- coding: utf-8 -*-
"""fixC2: записать в каталог Meyer перезапись подписей по плану fixC2-plan.json (дроп) + флаги ЛПР.

    python3 zapusk_na_servere.py fixC2_zapis.py [--primenit]

  0. копия каталога (backup API) в C:\\centro2\\_bekap\\fixC2-<время>\\ – НЕ для отката целиком;
  1. одна короткая транзакция: правка пишется, только если в живой базе ИНН, номер и КАЖДОЕ правимое
     поле равны ожидаемым из плана (иначе – пропуск в журнал); компании и контакты агента F2
     (bylo_fixF2, «дубль номера», ШКХП, Выбор Сибири, Морошка, Кардаильский, Донецкий БКК) не
     трогаются; прежнее значение – в bylo_fixC и в журнал; новые номера – если такого номера у
     компании ещё нет; старые колонки роли (is_tech/is_purchaser/has_role/nomer_ne_lichnyy) – по
     новой роли у затронутых номеров;
  2. флаги ЛПР затронутых компаний – contacts() кода панели; lpr_kratko по правилу fixF2
     («ФИО+мобильный → мобильный → первый ЛПР»); ступень очереди до/после (800/600/400/200/0);
  3. журнал «было → стало» – fixC2-zhurnal-<время>.json и .csv на дроп.
Без --primenit – сухой прогон (откат). Балл очереди после записи пересчитывает fixF2_ball.py --tolko-ball.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'
PLAN = os.path.join(DROP, 'fixC2-plan.json')
PRIMENIT = '--primenit' in sys.argv
F2_INN = {'3524015320', '2225132970', '9723051780', '3623007585', '9303024328'}

if '--vnutri' not in sys.argv:
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1600, cwd=KOREN, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5800:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)

sys.path.insert(0, KOREN)
import zapusk  # noqa: F401,E402
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
os.environ['CENTRIFUGAL_DB'] = KAT
from app.services import centro_catalog as cat  # noqa: E402

VREMYA = time.strftime('%Y%m%d-%H%M%S')
plan = json.load(io.open(PLAN, encoding='utf-8'))
zh = {'vremya': VREMYA, 'suhoy': not PRIMENIT, 'kontakty': [], 'novye': [], 'kompanii': [], 'propuski': []}


def tier(c, items):
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    if str(c.get('pometka_ocheredi') or '').strip():
        return 0
    return 800 if [x for x in mob if x['person']] else 600 if mob else 400 if lpr else 200


def pokaz(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


def flagi(items):
    """Как fixF2_dannye.flagi: lpr_kratko – ФИО+мобильный → мобильный → первый ЛПР."""
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    sprosit = [x for x in items if x['kind'] == 'sprosit']
    roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
    fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    if lpr:
        l0 = (fio_mob or mob or lpr)[0]
        kr = ' · '.join(v for v in (l0['person'], l0['position'] or l0['rol_vid'], pokaz(l0['value'])) if v)
        if len(lpr) > 1:
            kr += ' (+ ещё %d)' % (len(lpr) - 1)
    elif sprosit:
        s0 = sprosit[0]
        kr = '%s · %s (без номера – спросить у приёмной)' % (s0['person'], s0['position'] or s0['rol_vid'])
    else:
        put_ = [x for x in tel if x['has_role']]
        if put_:
            p0 = put_[0]
            kr = ('ЛПР не найден, через приёмную: %s' if p0['rol_vid'] in ('приёмная', 'общий номер')
                  else 'ЛПР не найден, номер с сайта: %s') % pokaz(p0['value'])
            n_mob = sum(1 for x in tel if x['vid_nomera'] == 'мобильный')
            if n_mob:
                kr += ' (мобильных без ЛПР: %d)' % n_mob
        else:
            kr = 'ЛПР не найден' + (', номера только неличные: %d' % len(tel) if tel else ', номеров нет')
    return {'has_tech': int(any(x['is_tech'] for x in lpr)),
            'n_tech': sum(1 for x in lpr if x['is_tech']),
            'has_purchaser': int(any(x['is_purchaser'] for x in lpr)),
            'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
            'lpr_mobilnyy': int(bool(mob)),
            'lpr_s_fio': len(fio_lpr),
            'lpr_roli': ', '.join(roli),
            'lpr_kratko': kr,
            'n_phones': len(tel), 'has_phone': int(bool(tel))}


def k10_dob(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return cat._phone_key(osn), dob


# ------------------------------------------------------------------ 0. копия
if PRIMENIT:
    BEKAP = os.path.join(KOREN, '_bekap', 'fixC2-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    src = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    dst = sqlite3.connect(os.path.join(BEKAP, 'meyer_baza1.db'))
    src.backup(dst)
    dst.close()
    src.close()
    print('копия каталога: %s' % BEKAP)

k = sqlite3.connect(KAT, timeout=30)
k.row_factory = sqlite3.Row
k.execute('PRAGMA busy_timeout=30000')
KOL = {r[1] for r in k.execute('PRAGMA table_info(contact)')}
inns = sorted({p['inn'] for p in plan['pravki']} | {n['inn'] for n in plan['novye']})
kompanii = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company WHERE inn IN (%s)' % ','.join('?' * len(inns)), inns)}
do_tier = {inn: tier(kompanii[inn], cat.contacts(inn)) for inn in inns if inn in kompanii}
k.commit()


def bylo_dobavit(staroe, polya_bylo, pochemu):
    try:
        b = json.loads(staroe) if staroe else []
    except ValueError:
        b = [{'nerazobrano': staroe}]
    b.append({'fixC2': VREMYA, 'pochemu': pochemu, 'bylo': polya_bylo})
    return json.dumps(b, ensure_ascii=False)


k.execute('BEGIN IMMEDIATE')
try:
    tronuty = set()
    for p in plan['pravki']:
        r = k.execute('SELECT * FROM contact WHERE id=?', (p['id'],)).fetchone()
        prich = None
        if not r or r['inn'] != p['inn'] or str(r['value']).strip() != str(p['value']).strip():
            prich = 'контакт изменился (ИНН/номер)'
        elif p['inn'] in F2_INN or ('bylo_fixF2' in KOL and (r['bylo_fixF2'] or '').strip()) \
                or (r['rol_vruchnuyu'] or '') == 'дубль номера':
            prich = 'правка агента F2 – не трогаю'
        else:
            for pole, ozh in p['ozhid'].items():
                if (r[pole] or '') != (ozh or ''):
                    prich = 'поле %s в живой базе «%s», ожидалось «%s»' % (pole, r[pole], ozh)
                    break
        if prich:
            zh['propuski'].append({'id': p['id'], 'inn': p['inn'], 'pochemu': prich})
            continue
        izm = {pole: v for pole, v in p['polya'].items() if pole in KOL}
        bylo = {pole: r[pole] for pole in izm}
        izm['bylo_fixC'] = bylo_dobavit(r['bylo_fixC'], bylo, p['pochemu'])
        k.execute('UPDATE contact SET %s WHERE id=?' % ', '.join('%s=?' % x for x in izm), list(izm.values()) + [p['id']])
        tronuty.add(p['id'])
        zh['kontakty'].append({'id': p['id'], 'inn': p['inn'], 'nomer': p['value'], 'gruppa': p['gruppa'],
                               'pochemu': p['pochemu'], 'bylo': bylo,
                               'stalo': {x: v for x, v in izm.items() if x != 'bylo_fixC'}})
    for n in plan['novye']:
        est = {k10_dob(r['value']) for r in k.execute("SELECT value FROM contact WHERE inn=? AND kind='phone'", (n['inn'],))}
        if k10_dob(n['value']) in est or n['inn'] in F2_INN:
            zh['propuski'].append({'inn': n['inn'], 'nomer': n['value'], 'pochemu': 'номер уже есть / компания F2'})
            continue
        rk = cat.rol_kontakta({'position': n['position']})
        vid = cat.vid_nomera_po_cifram(n['value'])
        stroka = {'inn': n['inn'], 'value': n['value'], 'kind': 'phone', 'person': n['person'],
                  'role': rk['vid'] if rk['lpr'] else '', 'position': n['position'], 'phone_type': vid,
                  'source': 'страница сайта · разбор подписей 09.10 (fixC2): ' + n['pochemu'], 'source_url': n['url'],
                  'is_purchaser': rk['zakup'], 'is_tech': rk['teh'], 'has_role': rk['lpr'], 'is_unknown_owner': 0,
                  'nomer_ne_lichnyy': None if rk['lpr'] else rk['vid'], 'vid_nomera': vid,
                  'bylo_fixC': json.dumps([{'fixC2': VREMYA, 'dobavlen': n['pochemu']}], ensure_ascii=False)}
        stroka = {x: v for x, v in stroka.items() if x in KOL}
        cur = k.execute('INSERT INTO contact(%s) VALUES(%s)' % (','.join(stroka), ','.join('?' * len(stroka))),
                        list(stroka.values()))
        tronuty.add(cur.lastrowid)
        zh['novye'].append({'id': cur.lastrowid, **stroka})
    # старые колонки роли – по новой роли у затронутых номеров
    for kid in tronuty:
        r = k.execute('SELECT * FROM contact WHERE id=?', (kid,)).fetchone()
        rk = cat.rol_kontakta(dict(r))
        novoe = {'is_tech': rk['teh'], 'is_purchaser': rk['zakup'],
                 'nomer_ne_lichnyy': None if rk['lpr'] else rk['vid']}
        if rk['lpr']:
            novoe['has_role'] = 1
        izm = {x: v for x, v in novoe.items() if x in KOL and (r[x] or None) != (v or None)}
        if izm:
            k.execute('UPDATE contact SET %s WHERE id=?' % ', '.join('%s=?' % x for x in izm), list(izm.values()) + [kid])
            zh['kontakty'].append({'id': kid, 'inn': r['inn'], 'nomer': r['value'], 'gruppa': 'старые колонки роли',
                                   'pochemu': 'по новой роли «%s»' % rk['vid'],
                                   'bylo': {x: r[x] for x in izm}, 'stalo': izm})
    if PRIMENIT:
        k.commit()
    else:
        k.rollback()
except Exception:
    k.rollback()
    raise

# ------------------------------------------------------------------ 2. флаги и ступени затронутых компаний
if PRIMENIT:
    obnov = []
    for inn in inns:
        c = kompanii.get(inn)
        if not c:
            continue
        items = cat.contacts(inn)
        novoe = flagi(items)
        izm = {x: v for x, v in novoe.items() if c.get(x) != v}
        posle = tier(c, items)
        zh['kompanii'].append({'inn': inn, 'bazy': c.get('bazy'), 'stupen_bylo': do_tier.get(inn), 'stupen_stalo': posle,
                               'bylo': {x: c.get(x) for x in izm}, 'stalo': izm})
        if izm:
            obnov.append((inn, izm))
    k.execute('BEGIN IMMEDIATE')
    try:
        for inn, izm in obnov:
            k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('%s=?' % x for x in izm), list(izm.values()) + [inn])
        k.commit()
    except Exception:
        k.rollback()
        raise
k.close()

# ------------------------------------------------------------------ 3. журнал
hv = '' if PRIMENIT else '-suhoy'
put = os.path.join(DROP, 'fixC2-zhurnal-%s%s.json' % (VREMYA, hv))
io.open(put, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=1))
with io.open(put[:-5] + '.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['таблица', 'id/ИНН', 'ИНН', 'номер', 'поле', 'было', 'стало', 'группа', 'почему'])
    for e in zh['kontakty']:
        for x, v in e['stalo'].items():
            w.writerow(['contact', e['id'], e['inn'], e['nomer'], x, e['bylo'].get(x), v, e['gruppa'], e['pochemu']])
    for e in zh['novye']:
        w.writerow(['contact (новый)', e['id'], e['inn'], e['value'], '*', '', '%s | %s' % (e.get('person'), e.get('position')), 'новый', e.get('source')])
    for e in zh['kompanii']:
        w.writerow(['company', e['inn'], e['inn'], '', 'ступень', e['stupen_bylo'], e['stupen_stalo'], '', ''])
        for x, v in e['stalo'].items():
            w.writerow(['company', e['inn'], e['inn'], '', x, e['bylo'].get(x), v, '', 'пересчёт флагов ЛПР'])
print('%s: правок контактов %d (в т. ч. старые колонки), новых номеров %d, компаний %d, пропусков %d'
      % ('ЗАПИСАНО' if PRIMENIT else 'СУХОЙ ПРОГОН (откат)', len(zh['kontakty']), len(zh['novye']),
         len(zh['kompanii']), len(zh['propuski'])))
print('по группам:', dict(collections.Counter(e['gruppa'] for e in zh['kontakty'])))
print('ступени:', [(e['inn'], e['stupen_bylo'], e['stupen_stalo']) for e in zh['kompanii'] if e['stupen_bylo'] != e['stupen_stalo']])
print('пропуски:', json.dumps(zh['propuski'], ensure_ascii=False)[:1500])
print('журнал: %s (+ .csv)' % put)
