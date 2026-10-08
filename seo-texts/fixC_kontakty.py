# -*- coding: utf-8 -*-
"""fixC: запись правок контактов и людей в каталог Meyer + пересчёт флагов ЛПР компаний.

    python3 zapusk_na_servere.py fixC_kontakty.py [--primenit]
    (локально: python3 fixC_kontakty.py --lokalno <каталог.db> <корень app> <plan.json> --primenit)

План (fixC-plan.json на дропе) собирает fixC_plan.py по страницам-источникам. Здесь:
  0. копия каталога (backup API) в C:\\centro2\\_bekap\\fixC-<время>\\ – НЕ для отката целиком;
  1. колонки (ADD COLUMN, если нет): contact.vid_nomera, vid_pochemu, rol_vruchnuyu,
     podpis_stranicy, bylo_fixC, chuzhoy_istochnik; person.chuzhoy_istochnik,
     sprosit_u_priemnoy, bylo_fixC;
  2. одна короткая транзакция: правки контактов по id (сверка ИНН + номера; изменился –
     пропуск), новые номера (с источником «страница сайта · разбор подписей»), люди без
     телефона («спросить у приёмной»), пометка людей с чужих страниц, согласование старых
     колонок is_tech/is_purchaser/has_role/nomer_ne_lichnyy с новой ролью;
  3. флаги ЛПР компании (has_tech, n_tech, has_purchaser, n_purchaser, lpr_mobilnyy, lpr_s_fio,
     lpr_roli, lpr_kratko, n_phones, has_phone) – той же функцией contacts(), что рисует
     карточку (код панели уже с правкой fixC_kod.py);
  4. журнал «было → стало» построчно – fixC-zhurnal-kontakty-<время>.json на дроп.
Без --primenit – сухой прогон (транзакция откатывается, журнал пишется с пометкой «сухой»).
Ничего не удаляет.
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
DROP = r'C:\seostat\drop\drop-storage'
PLAN = os.path.join(DROP, 'fixC-plan.json')
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

assert hasattr(cat, 'rol_kontakta'), 'в коде панели нет правки fixC (сначала fixC_kod.py)'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
plan = json.load(io.open(PLAN, encoding='utf-8'))
zhurnal = {'vremya': VREMYA, 'suhoy': not PRIMENIT, 'kontakty': [], 'novye': [], 'lyudi': [], 'kompanii': [],
           'propuski': []}


def k10_dob(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return cat._phone_key(osn), dob


def podklyuchit():
    for popytka in range(8):
        try:
            k = sqlite3.connect(KAT, timeout=30)
            k.row_factory = sqlite3.Row
            k.execute('PRAGMA busy_timeout=30000')
            return k
        except sqlite3.OperationalError:
            time.sleep(2)
    raise SystemExit('каталог недоступен')


# ------------------------------------------------------------------ 0. копия каталога
if PRIMENIT and not LOKALNO:
    BEKAP = os.path.join(KOREN, '_bekap', 'fixC-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    src = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    dst = sqlite3.connect(os.path.join(BEKAP, 'meyer_baza1.db'))
    src.backup(dst)
    dst.close()
    src.close()
    print('копия каталога: %s' % BEKAP)

k = podklyuchit()
# ------------------------------------------------------------------ 1. колонки
for tab, kol in (('contact', ('vid_nomera', 'vid_pochemu', 'rol_vruchnuyu', 'podpis_stranicy', 'bylo_fixC',
                              'chuzhoy_istochnik')),
                 ('person', ('chuzhoy_istochnik', 'sprosit_u_priemnoy', 'bylo_fixC'))):
    est = {r[1] for r in k.execute('PRAGMA table_info(%s)' % tab)}
    for c in kol:
        if c not in est:
            k.execute('ALTER TABLE %s ADD COLUMN %s TEXT' % (tab, c))
            print('добавлена колонка %s.%s' % (tab, c))
k.commit()
KOL_C = {r[1] for r in k.execute('PRAGMA table_info(contact)')}
KOL_P = {r[1] for r in k.execute('PRAGMA table_info(person)')}


def bylo_dobavit(staroe_json, polya_bylo):
    try:
        b = json.loads(staroe_json) if staroe_json else []
    except ValueError:
        b = [{'nerazobrano': staroe_json}]
    b.append({'fixC': VREMYA, 'bylo': polya_bylo})
    return json.dumps(b, ensure_ascii=False)


# ------------------------------------------------------------------ 2. транзакция
k.execute('BEGIN IMMEDIATE')
try:
    # 2а. правки контактов
    for o in plan['obnovit']:
        r = k.execute('SELECT * FROM contact WHERE id=?', (o['id'],)).fetchone()
        if not r or r['inn'] != o['inn'] or str(r['value']).strip() != str(o['value']).strip():
            zhurnal['propuski'].append({'id': o['id'], 'pochemu': 'контакт изменился или удалён после разбора'})
            continue
        polya = {p: v for p, v in o['polya'].items() if p in KOL_C}
        bylo = {p: r[p] for p in polya}
        izm = {p: v for p, v in polya.items() if (r[p] or '') != (v or '')}
        if not izm:
            continue
        izm['bylo_fixC'] = bylo_dobavit(r['bylo_fixC'] if 'bylo_fixC' in KOL_C else '', {p: bylo[p] for p in izm})
        k.execute('UPDATE contact SET %s WHERE id=?' % ', '.join('%s=?' % p for p in izm), list(izm.values()) + [o['id']])
        zhurnal['kontakty'].append({'id': o['id'], 'inn': o['inn'], 'nomer': o['value'], 'pochemu': o['pochemu'],
                                    'bylo': {p: bylo[p] for p in izm if p != 'bylo_fixC'},
                                    'stalo': {p: v for p, v in izm.items() if p != 'bylo_fixC'}})
    # 2б. новые номера
    est_u = collections.defaultdict(set)
    for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
        est_u[r['inn']].add(k10_dob(r['value']))
    for n in plan['novye']:
        kd = k10_dob(n['value'])
        if kd in est_u[n['inn']]:
            zhurnal['propuski'].append({'inn': n['inn'], 'nomer': n['value'], 'pochemu': 'номер уже есть'})
            continue
        est_u[n['inn']].add(kd)
        rk = cat.rol_kontakta({'position': n['position'], 'source': n['source']})
        vid = cat.vid_nomera_po_cifram(n['value'])
        stroka = {'inn': n['inn'], 'value': n['value'], 'kind': 'phone', 'person': n['person'],
                  'role': rk['vid'] if rk['lpr'] else '', 'position': n['position'],
                  'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                  'source': n['source'], 'source_url': n['source_url'], 'fragment': n['fragment'],
                  'is_purchaser': rk['zakup'], 'is_tech': rk['teh'], 'has_role': rk['lpr'], 'is_unknown_owner': 0,
                  'nomer_ne_lichnyy': None if rk['lpr'] else rk['vid'], 'vid_nomera': vid,
                  'bylo_fixC': json.dumps([{'fixC': VREMYA, 'dobavlen': 'новый номер со страницы-источника',
                                            'ishod_id': n.get('ishod_id')}], ensure_ascii=False)}
        stroka = {p: v for p, v in stroka.items() if p in KOL_C}
        cur = k.execute('INSERT INTO contact(%s) VALUES(%s)' % (','.join(stroka), ','.join('?' * len(stroka))),
                        list(stroka.values()))
        zhurnal['novye'].append({'id': cur.lastrowid, **{p: v for p, v in stroka.items() if p != 'fragment'}})
    # 2в. люди без телефона – «спросить у приёмной»
    lyudi_po_inn = collections.defaultdict(set)
    for r in k.execute('SELECT inn, person FROM person'):
        lyudi_po_inn[r['inn']].add(cat._kl_fio(r['person']))
    for b in plan['lpr_bez_telefona']:
        if cat._kl_fio(b['person']) in lyudi_po_inn[b['inn']]:
            zhurnal['propuski'].append({'inn': b['inn'], 'person': b['person'], 'pochemu': 'человек уже есть в person'})
            continue
        lyudi_po_inn[b['inn']].add(cat._kl_fio(b['person']))
        rk = cat.rol_kontakta({'position': b['position']})
        stroka = {'inn': b['inn'], 'person': b['person'], 'position': b['position'], 'role': rk['vid'],
                  'phone': '', 'phone_type': '', 'email': '', 'source_url': b['source_url'],
                  'source': 'страница сайта · разбор подписей 08.10 (fixC): ЛПР без телефона на странице – спросить у приёмной',
                  'is_tech': rk['teh'], 'sprosit_u_priemnoy': b.get('primechanie') or 'да',
                  'bylo_fixC': json.dumps([{'fixC': VREMYA, 'dobavlen': 'ЛПР без телефона со страницы',
                                            'fragment': b.get('fragment', '')[:300]}], ensure_ascii=False)}
        stroka = {p: v for p, v in stroka.items() if p in KOL_P}
        cur = k.execute('INSERT INTO person(%s) VALUES(%s)' % (','.join(stroka), ','.join('?' * len(stroka))),
                        list(stroka.values()))
        zhurnal['lyudi'].append({'id': cur.lastrowid, 'deystvie': 'добавлен (спросить у приёмной)', **stroka})
    # 2г. люди со страниц другого юрлица – та же пометка, что у их номеров (агент D)
    chuzh = collections.defaultdict(list)
    for r in k.execute("SELECT inn, value, person, source_url, chuzhoy_istochnik FROM contact "
                       "WHERE TRIM(COALESCE(chuzhoy_istochnik,''))<>''"):
        chuzh[r['inn']].append(dict(r))
    svoi_domeny = collections.defaultdict(set)
    for r in k.execute("SELECT inn, source_url FROM contact WHERE TRIM(COALESCE(chuzhoy_istochnik,''))=''"):
        for u in str(r['source_url'] or '').replace(';', ' ').split():
            svoi_domeny[r['inn']].add(re.sub(r'^https?://(www\.)?', '', u).split('/')[0].lower())

    def domen(u):
        return re.sub(r'^https?://(www\.)?', '', str(u or '')).split('/')[0].lower()
    for r in k.execute('SELECT * FROM person').fetchall():
        if r['inn'] not in chuzh or (r['chuzhoy_istochnik'] or '').strip():
            continue
        tel = cat._phone_key(cat._razdelit_dobavochnyy(r['phone'])[0]) if r['phone'] else ''
        metka = ''
        for c in chuzh[r['inn']]:
            if (tel and tel == cat._phone_key(cat._razdelit_dobavochnyy(c['value'])[0])) or \
               (r['person'] and c['person'] and cat._kl_fio(r['person']) == cat._kl_fio(c['person'])) or \
               (domen(r['source_url']) and domen(r['source_url']) == domen(c['source_url'])
                    and domen(r['source_url']) not in svoi_domeny[r['inn']]):
                metka = c['chuzhoy_istochnik']
                break
        if metka:
            k.execute('UPDATE person SET chuzhoy_istochnik=?, bylo_fixC=? WHERE id=?',
                      (metka, bylo_dobavit(r['bylo_fixC'], {'chuzhoy_istochnik': None}), r['id']))
            zhurnal['lyudi'].append({'id': r['id'], 'inn': r['inn'], 'person': r['person'],
                                     'deystvie': 'помечен: человек со страницы другого юрлица', 'stalo': metka})
    # 2д. старые колонки ролей – в согласии с новой ролью (их читают другие места панели)
    for r in k.execute("SELECT * FROM contact WHERE kind='phone'").fetchall():
        rk = cat.rol_kontakta(dict(r))
        novoe = {'is_tech': rk['teh'], 'is_purchaser': rk['zakup']}
        if rk['lpr']:
            novoe['nomer_ne_lichnyy'] = None
            novoe['has_role'] = 1
        else:
            novoe['nomer_ne_lichnyy'] = rk['vid']
        izm = {p: v for p, v in novoe.items() if p in KOL_C and (r[p] if r[p] is not None else None) != v
               and not (p == 'nomer_ne_lichnyy' and (r[p] or '') == (v or ''))}
        if not izm:
            continue
        bylo = {p: r[p] for p in izm}
        k.execute('UPDATE contact SET %s, bylo_fixC=? WHERE id=?' % ', '.join('%s=?' % p for p in izm),
                  list(izm.values()) + [bylo_dobavit(r['bylo_fixC'], bylo), r['id']])
        zhurnal['kontakty'].append({'id': r['id'], 'inn': r['inn'], 'nomer': r['value'],
                                    'pochemu': 'старые колонки роли – по новой роли «%s»' % rk['vid'],
                                    'bylo': bylo, 'stalo': izm})
    if PRIMENIT:
        k.commit()
    else:
        k.rollback()
except Exception:
    k.rollback()
    raise

# ------------------------------------------------------------------ 3. флаги ЛПР компаний
def pokaz(v):
    """«+79000000000 доб. 12» -> «+7 900 000-00-00 доб. 12» (как в прежних lpr_kratko)."""
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


if PRIMENIT:
    kompanii = [dict(r) for r in k.execute('SELECT * FROM company')]
    k.commit()
    obnovleniya = []          # сначала всё считаем (чтение), потом короткая запись
    if True:
        for c in kompanii:
            items = cat.contacts(c['inn'])
            tel = [x for x in items if x['kind'] == 'phone']
            lpr = [x for x in tel if x['lpr']]
            sprosit = [x for x in items if x['kind'] == 'sprosit']
            roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
            fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
            # личный мобильный ЛПР; мобильный, общий у разных людей двух компаний, – линия, не личный
            mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
            if lpr:
                l0 = lpr[0]
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
            novoe = {'has_tech': int(any(x['is_tech'] for x in lpr)),
                     'n_tech': sum(1 for x in lpr if x['is_tech']),
                     'has_purchaser': int(any(x['is_purchaser'] for x in lpr)),
                     'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
                     'lpr_mobilnyy': int(bool(mob)),
                     'lpr_s_fio': len(fio_lpr),
                     'lpr_roli': ', '.join(roli),
                     'lpr_kratko': kr,
                     'n_phones': len(tel), 'has_phone': int(bool(tel))}
            izm = {p: v for p, v in novoe.items() if c.get(p) != v}
            if izm:
                obnovleniya.append((c, izm))
    k.execute('BEGIN IMMEDIATE')
    try:
        for c, izm in obnovleniya:
            k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('%s=?' % p for p in izm),
                      list(izm.values()) + [c['inn']])
            zhurnal['kompanii'].append({'inn': c['inn'], 'bazy': c.get('bazy'),
                                        'bylo': {p: c.get(p) for p in izm}, 'stalo': izm})
        k.commit()
    except Exception:
        k.rollback()
        raise
k.close()

# ------------------------------------------------------------------ 4. журнал
put_zh = os.path.join(DROP, 'fixC-zhurnal-kontakty-%s%s.json' % (VREMYA, '' if PRIMENIT else '-suhoy'))
io.open(put_zh, 'w', encoding='utf-8').write(json.dumps(zhurnal, ensure_ascii=False, indent=1))
print('%s: правок контактов %d, новых номеров %d, людей (добавлено/помечено) %d, компаний с новыми флагами %d, пропусков %d'
      % ('ПРИМЕНЕНО' if PRIMENIT else 'СУХОЙ ПРОГОН', len(zhurnal['kontakty']), len(zhurnal['novye']),
         len(zhurnal['lyudi']), len(zhurnal['kompanii']), len(zhurnal['propuski'])))
print('журнал: %s' % put_zh)
print(collections.Counter(p['pochemu'] for p in zhurnal['propuski']).most_common(5))
