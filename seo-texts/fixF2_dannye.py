# -*- coding: utf-8 -*-
"""fixF2: доводка данных контактов каталога Meyer по повторной проверке (08.10) + флаги ЛПР компаний.

    python3 zapusk_na_servere.py fixF2_dannye.py [--primenit]
    локально: python3 fixF2_dannye.py --lokalno <каталог.db> <корень с app> <fixF2-plan.json> [--primenit]

План (fixF2-plan.json на дропе, номера телефонов – только в нём) собирает fixF2_plan.py. Здесь:
  0. копии каталога и базы продаж (backup API) в C:\\centro2\\_bekap\\fixF2-<время>\\ – НЕ для отката
     целиком (по ним fixF2_proverka.py рисует очередь «до»);
  1. колонки (ADD COLUMN, если нет): contact.svyaz_adres, chuzhoy_istochnik_ishodnyy, bylo_fixF2;
     person.bylo_fixF2; company.proverka_sayta_ishodnaya, bylo_fixF2;
  2. одна короткая транзакция: правки контактов/людей/компаний по id (значение пишется, только
     если в живой базе стоит то же, что было в копии при плане; иначе пропуск в журнал), новые
     люди и номера (если такого номера/человека у компании ещё нет), старые колонки роли
     (is_tech/is_purchaser/has_role/nomer_ne_lichnyy) – по новой роли у затронутых компаний;
     ПЕРЕД commit – роль каждого правленого номера считается той же rol_kontakta() и сверяется с
     ожидаемой; не совпало – откат всего;
  3. флаги ЛПР ВСЕХ компаний – как у fixC (contacts() той же функцией, что рисует карточку), но
     lpr_kratko показывает лучший контакт, по которому дана ступень очереди: ЛПР с ФИО и мобильным
     (800) → ЛПР с мобильным (600) → первый ЛПР (400); прежде – всегда первый ЛПР карточки
     (у УОМЗ 3525279862 – городской главного инженера при ступени 800 за мобильный коммерческого);
  4. журнал «было → стало» – fixF2-zhurnal-dannye-<время>.json и .csv на дроп.
Без --primenit – сухой прогон: транзакция откатывается, флаги не пишутся. Ничего не удаляет.
"""
import collections
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
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PLAN = os.path.join(DROP, 'fixF2-plan.json')
LOKALNO = '--lokalno' in sys.argv
if LOKALNO:
    i = sys.argv.index('--lokalno')
    KAT, KOREN_APP, PLAN = sys.argv[i + 1:i + 4]
    DROP = os.path.dirname(os.path.abspath(PLAN))
PRIMENIT = '--primenit' in sys.argv

if not LOKALNO and '--vnutri' not in sys.argv:
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1600, cwd=KOREN, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5800:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)

os.environ['CENTRIFUGAL_DB'] = KAT
if LOKALNO:
    sys.path.insert(0, KOREN_APP)
else:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401,E402
    import logging  # noqa: E402
    logging.disable(logging.CRITICAL)
    assert os.path.normcase(os.environ.get('CENTRIFUGAL_DB', KAT)) == os.path.normcase(KAT)
from app.services import centro_catalog as cat  # noqa: E402

VREMYA = time.strftime('%Y%m%d-%H%M%S')
plan = json.load(io.open(PLAN, encoding='utf-8'))
zhurnal = {'vremya': VREMYA, 'suhoy': not PRIMENIT, 'kontakty': [], 'lyudi': [], 'novye_lyudi': [], 'novye_kontakty': [],
           'kompanii': [], 'flagi': [], 'propuski': [], 'rol_proverka': []}


def pust(v):
    return '' if v is None else str(v)


def podklyuchit(put):
    for popytka in range(8):
        try:
            k = sqlite3.connect(put, timeout=30)
            k.row_factory = sqlite3.Row
            k.execute('PRAGMA busy_timeout=30000')
            return k
        except sqlite3.OperationalError:
            time.sleep(2)
    raise SystemExit('база недоступна: %s' % put)


def kopiya(src_put, dst_put):
    src = sqlite3.connect('file:%s?mode=ro' % src_put, uri=True)
    dst = sqlite3.connect(dst_put)
    src.backup(dst)
    dst.close()
    src.close()


def bylo_dobavit(staroe_json, polya_bylo, pochemu):
    try:
        b = json.loads(staroe_json) if staroe_json else []
    except ValueError:
        b = [{'nerazobrano': staroe_json}]
    b.append({'fixF2': VREMYA, 'pochemu': pochemu, 'bylo': polya_bylo})
    return json.dumps(b, ensure_ascii=False)


def k10_dob(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return cat._phone_key(osn), dob


# ------------------------------------------------------------------ 0. копии баз
if PRIMENIT and not LOKALNO:
    BEKAP = os.path.join(KOREN, '_bekap', 'fixF2-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    kopiya(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
    kopiya(SALES, os.path.join(BEKAP, 'centro_sales_meyer1.db'))
    zhurnal['bekap'] = BEKAP
    print('копии баз (НЕ для отката целиком): %s' % BEKAP)

k = podklyuchit(KAT)
# ------------------------------------------------------------------ 1. колонки
for tab, kol in (('contact', ('svyaz_adres', 'chuzhoy_istochnik_ishodnyy', 'bylo_fixF2')),
                 ('person', ('bylo_fixF2',)),
                 ('company', ('proverka_sayta_ishodnaya', 'bylo_fixF2'))):
    est = {r[1] for r in k.execute('PRAGMA table_info(%s)' % tab)}
    for c in kol:
        if c not in est:                     # колонки добавляются и в сухом прогоне (только добавление)
            k.execute('ALTER TABLE %s ADD COLUMN %s TEXT' % (tab, c))
            print('добавлена колонка %s.%s' % (tab, c))
k.commit()
KOL = {t: {r[1] for r in k.execute('PRAGMA table_info(%s)' % t)} for t in ('contact', 'person', 'company')}


def obnovit(tab, klyuch, znach, polya, ozhid, pochemu, rec):
    """UPDATE одной строки, если её поля сейчас такие же, как в копии при плане (ozhid)."""
    r = k.execute('SELECT * FROM %s WHERE %s=?' % (tab, klyuch), (znach,)).fetchone()
    if not r:
        zhurnal['propuski'].append({'tab': tab, klyuch: znach, 'pochemu': 'строки нет'})
        return False
    r = dict(r)
    for p, ov in rec.items():
        if pust(r.get(p)).strip() != pust(ov).strip():
            zhurnal['propuski'].append({'tab': tab, klyuch: znach, 'pochemu': 'изменилась строка (%s)' % p})
            return False
    pl = {p: v for p, v in polya.items() if p in KOL[tab]}
    for p, ov in ozhid.items():
        if p in r and pust(r.get(p)) != pust(ov):
            zhurnal['propuski'].append({'tab': tab, klyuch: znach, 'pole': p, 'v_kopii': ov, 'seychas': r.get(p),
                                        'pochemu': 'поле изменено после плана'})
            return False
    izm = {p: v for p, v in pl.items() if pust(r.get(p)) != pust(v)}
    if not izm:
        return False
    bylo = {p: r.get(p) for p in izm}
    if 'bylo_fixF2' in KOL[tab]:
        izm['bylo_fixF2'] = bylo_dobavit(r.get('bylo_fixF2'), bylo, pochemu)
    k.execute('UPDATE %s SET %s WHERE %s=?' % (tab, ', '.join('%s=?' % p for p in izm), klyuch),
              list(izm.values()) + [znach])
    return {'bylo': bylo, 'stalo': {p: v for p, v in izm.items() if p != 'bylo_fixF2'}}


# ------------------------------------------------------------------ 2. транзакция
k.execute('BEGIN IMMEDIATE')
zatronuty = set()
try:
    for o in plan['kontakty']:
        rez = obnovit('contact', 'id', o['id'], o['novoe'], o['ozhid'], o['pochemu'],
                      {'inn': o['inn'], 'value': o['value']})
        if rez:
            zatronuty.add(o['inn'])
            zhurnal['kontakty'].append({'id': o['id'], 'inn': o['inn'], 'nomer': o['value'], 'pochemu': o['pochemu'], **rez})
    for o in plan['lyudi']:
        rez = obnovit('person', 'id', o['id'], o['novoe'], o['ozhid'], o['pochemu'],
                      {'inn': o['inn'], 'person': o['person']})
        if rez:
            zatronuty.add(o['inn'])
            zhurnal['lyudi'].append({'id': o['id'], 'inn': o['inn'], 'person': o['person'], 'pochemu': o['pochemu'], **rez})
    for o in plan['kompanii']:
        rez = obnovit('company', 'inn', o['inn'], o['novoe'], o['ozhid'], o['pochemu'], {})
        if rez:
            zhurnal['kompanii'].append({'inn': o['inn'], 'pochemu': o['pochemu'], **rez})
    # новые люди без телефона («спросить у приёмной»)
    for n in plan['novye_lyudi']:
        est = {cat._kl_fio(r['person']) for r in k.execute('SELECT person FROM person WHERE inn=?', (n['inn'],))}
        if cat._kl_fio(n['person']) in est:
            zhurnal['propuski'].append({'inn': n['inn'], 'person': n['person'], 'pochemu': 'человек уже есть'})
            continue
        rk = cat.rol_kontakta({'position': n['position']})
        stroka = {'inn': n['inn'], 'person': n['person'], 'position': n['position'], 'role': rk['vid'], 'phone': '',
                  'phone_type': '', 'email': n['email'], 'source_url': n['source_url'], 'source': n['source'],
                  'is_tech': rk['teh'], 'sprosit_u_priemnoy': n['sprosit_u_priemnoy'],
                  'bylo_fixF2': json.dumps([{'fixF2': VREMYA, 'dobavlen': 'ЛПР без телефона со страницы'}], ensure_ascii=False)}
        stroka = {p: v for p, v in stroka.items() if p in KOL['person']}
        cur = k.execute('INSERT INTO person(%s) VALUES(%s)' % (','.join(stroka), ','.join('?' * len(stroka))),
                        list(stroka.values()))
        zatronuty.add(n['inn'])
        zhurnal['novye_lyudi'].append({'id': cur.lastrowid, **stroka})
        if n.get('ozhid_rol'):
            zhurnal['rol_proverka'].append(('person %s' % cur.lastrowid, n['ozhid_rol'], rk['vid']))
    # новые номера (добавочные со страницы)
    for n in plan['novye_kontakty']:
        est = {k10_dob(r['value']) for r in k.execute("SELECT value FROM contact WHERE inn=? AND kind='phone'", (n['inn'],))}
        if k10_dob(n['value']) in est:
            zhurnal['propuski'].append({'inn': n['inn'], 'nomer': n['value'], 'pochemu': 'номер уже есть'})
            continue
        vid = cat.vid_nomera_po_cifram(n['value'])
        stroka = {'inn': n['inn'], 'value': n['value'], 'kind': 'phone', 'person': n['person'], 'position': n['position'],
                  'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                  'source': n['source'], 'source_url': n['source_url'], 'fragment': n['fragment'],
                  'is_unknown_owner': 0, 'vid_nomera': vid, 'svyaz_adres': n['svyaz_adres'], 'vid_pochemu': n['vid_pochemu'],
                  'rol_vruchnuyu': n['rol_vruchnuyu'], 'podpis_stranicy': n['podpis_stranicy'],
                  'bylo_fixF2': json.dumps([{'fixF2': VREMYA, 'dobavlen': 'добавочный со страницы связанного юрлица (тот же адрес)'}],
                                           ensure_ascii=False)}
        rk = cat.rol_kontakta(stroka)
        stroka.update({'role': rk['vid'] if rk['lpr'] else '', 'is_purchaser': rk['zakup'], 'is_tech': rk['teh'],
                       'has_role': rk['lpr'], 'nomer_ne_lichnyy': None if rk['lpr'] else rk['vid']})
        stroka = {p: v for p, v in stroka.items() if p in KOL['contact']}
        cur = k.execute('INSERT INTO contact(%s) VALUES(%s)' % (','.join(stroka), ','.join('?' * len(stroka))),
                        list(stroka.values()))
        zatronuty.add(n['inn'])
        zhurnal['novye_kontakty'].append({'id': cur.lastrowid, **{p: v for p, v in stroka.items() if p != 'fragment'}})
        if n.get('ozhid_rol'):
            zhurnal['rol_proverka'].append(('contact %s' % cur.lastrowid, n['ozhid_rol'], rk['vid']))
    # роль правленых номеров – той же функцией, что рисует карточку
    for kl, ozh in plan['ozhid_rol'].items():
        r = k.execute('SELECT * FROM contact WHERE id=?', (int(kl[1:]),)).fetchone()
        if r:
            zhurnal['rol_proverka'].append(('contact %s' % kl[1:], ozh, cat.rol_kontakta(dict(r))['vid']))
    ne_te = [x for x in zhurnal['rol_proverka'] if x[1] != x[2]]
    print('проверка ролей до commit: %d из %d совпали%s' % (len(zhurnal['rol_proverka']) - len(ne_te),
                                                             len(zhurnal['rol_proverka']), ('; НЕ совпали: %s' % ne_te) if ne_te else ''))
    if ne_te:
        raise RuntimeError('роль не та, что ожидалась – откат')
    # старые колонки роли – по новой роли (их читают другие места панели), только у затронутых компаний
    for r in k.execute("SELECT * FROM contact WHERE kind='phone' AND inn IN (%s)" % ','.join('?' * len(zatronuty)),
                       sorted(zatronuty)).fetchall():
        rk = cat.rol_kontakta(dict(r))
        novoe = {'is_tech': rk['teh'], 'is_purchaser': rk['zakup']}
        if rk['lpr']:
            novoe['nomer_ne_lichnyy'] = None
            novoe['has_role'] = 1
        else:
            novoe['nomer_ne_lichnyy'] = rk['vid']
        izm = {p: v for p, v in novoe.items() if p in KOL['contact'] and r[p] != v
               and not (p == 'nomer_ne_lichnyy' and (r[p] or '') == (v or ''))}
        if not izm:
            continue
        bylo = {p: r[p] for p in izm}
        izm['bylo_fixF2'] = bylo_dobavit(r['bylo_fixF2'] if 'bylo_fixF2' in KOL['contact'] else '', bylo,
                                         'старые колонки роли – по новой роли «%s»' % rk['vid'])
        if 'bylo_fixF2' not in KOL['contact']:
            del izm['bylo_fixF2']
        k.execute('UPDATE contact SET %s WHERE id=?' % ', '.join('%s=?' % p for p in izm), list(izm.values()) + [r['id']])
        zhurnal['kontakty'].append({'id': r['id'], 'inn': r['inn'], 'nomer': r['value'],
                                    'pochemu': 'старые колонки роли – по новой роли «%s»' % rk['vid'],
                                    'bylo': bylo, 'stalo': {p: v for p, v in izm.items() if p != 'bylo_fixF2'}})
    if PRIMENIT:
        k.commit()
    else:
        k.rollback()
except Exception:
    k.rollback()
    raise
print('%s: правок контактов %d, людей %d, новых людей %d, новых номеров %d, компаний %d, пропусков %d'
      % ('ЗАПИСАНО' if PRIMENIT else 'СУХОЙ ПРОГОН (откат)', len(zhurnal['kontakty']), len(zhurnal['lyudi']),
         len(zhurnal['novye_lyudi']), len(zhurnal['novye_kontakty']), len(zhurnal['kompanii']), len(zhurnal['propuski'])))
if zhurnal['propuski']:
    print('пропуски:', json.dumps(zhurnal['propuski'][:12], ensure_ascii=False)[:1500])


# ------------------------------------------------------------------ 3. флаги ЛПР компаний
def pokaz(v):
    """«+79000000000 доб. 12» -> «+7 900 000-00-00 доб. 12» (как в прежних lpr_kratko)."""
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


def flagi(items):
    """Флаги ЛПР компании по контактам карточки. lpr_kratko – лучший контакт, по которому дана
    ступень очереди (fixE2: 800 ЛПР с ФИО и мобильным, 600 ЛПР с мобильным, 400 ЛПР с рабочим)."""
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


if PRIMENIT:
    kompanii = [dict(r) for r in k.execute('SELECT * FROM company')]
    obnovleniya = []
    for c in kompanii:
        novoe = flagi(cat.contacts(c['inn']))
        izm = {p: v for p, v in novoe.items() if c.get(p) != v}
        if izm:
            obnovleniya.append((c, izm))
    k.execute('BEGIN IMMEDIATE')
    try:
        for c, izm in obnovleniya:
            k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('%s=?' % p for p in izm),
                      list(izm.values()) + [c['inn']])
            zhurnal['flagi'].append({'inn': c['inn'], 'bylo': {p: c.get(p) for p in izm}, 'stalo': izm})
        k.commit()
    except Exception:
        k.rollback()
        raise
    print('флаги ЛПР: изменены у %d компаний из %d (lpr_kratko – у %d)'
          % (len(zhurnal['flagi']), len(kompanii), sum(1 for f in zhurnal['flagi'] if 'lpr_kratko' in f['stalo'])))
k.close()

# ------------------------------------------------------------------ 4. журнал
hv = '' if PRIMENIT else '-suhoy'
put_zh = os.path.join(DROP, 'fixF2-zhurnal-dannye-%s%s.json' % (VREMYA, hv))
io.open(put_zh, 'w', encoding='utf-8').write(json.dumps(zhurnal, ensure_ascii=False, indent=1))
put_csv = os.path.join(DROP, 'fixF2-zhurnal-dannye-%s%s.csv' % (VREMYA, hv))
with io.open(put_csv, 'w', encoding='utf-8-sig', newline='') as f:
    f.write('Таблица;Ключ;ИНН;Поле;Было;Стало;Почему\n')

    def cs(v):
        return str('' if v is None else v).replace(';', ',').replace('\n', ' ')[:400]
    for t, spis, kl in (('contact', zhurnal['kontakty'], 'id'), ('person', zhurnal['lyudi'], 'id'),
                        ('company', zhurnal['kompanii'], 'inn'), ('company-флаги', zhurnal['flagi'], 'inn')):
        for z in spis:
            for p, v in z['stalo'].items():
                f.write(';'.join(cs(x) for x in (t, z[kl], z['inn'], p, z['bylo'].get(p), v, z.get('pochemu', ''))) + '\n')
    for t, spis in (('contact-новый', zhurnal['novye_kontakty']), ('person-новый', zhurnal['novye_lyudi'])):
        for z in spis:
            f.write(';'.join(cs(x) for x in (t, z['id'], z['inn'], 'вся строка', '', json.dumps(z, ensure_ascii=False), 'добавлен')) + '\n')
print('журнал: %s; %s' % (put_zh, put_csv))
