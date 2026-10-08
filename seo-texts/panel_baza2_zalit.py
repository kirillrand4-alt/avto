# -*- coding: utf-8 -*-
"""Заливка «Базы 2» Meyer (файл 2, «ЛПР, остальные телефоны») – копия загрузчика Базы 4.

Владелец 08.10: «из 2 и 4 базы взять только полезное», «загрузи 30». Из файла 2 – 30
компаний (ЛПР, сверено, свой сайт, основной ОКВЭД, выручка от 100 млн или неизвестна);
9 компаний, уже стоящих в панели, получают метку «База 2» и новые номера.

Ниже – описание загрузчика Базы 6, всё в силе.

Что делается:
  1. Снимок назначений и статусов до заливки (для проверки «ничего чужого не тронуто»).
  2. НАЗНАЧЕНИЯ ПИШУТСЯ ПЕРВЫМИ. Панель на каждой загрузке страницы раздаёт «новые» ИНН
     каталога сама (assign_new, со случайностью внутри групп балла). Если бы каталог
     пополнился раньше, первая же открытая страница раздала бы Базу 6 по-своему.
  3. Раздача: поровну по баллу панели (company_score – та же формула, что у Базы 1),
     холдинг целиком одному продавцу; если кто-то из группы уже у продавца (База 1) –
     группа идёт к нему.
  4. Каталог одной транзакцией: компании, все номера (ЛПР наверху, прочие – «остальные» с
     видом номера), люди, источники ЛПР, состав холдингов. Ошибка – откат каталога и
     удаление назначений из шага 2.
  5. Три компании, уже стоящие в Базе 1, не дублируются: метка «База 1 | База 6», новые
     номера (если такого номера у компании ещё нет), пустые поля дополняются.
  6. Код: добавочный номер («+7 495 000-00-00 доб. 212» – раньше сливался в
     «+74950000000212», и tel:-ссылка набирала мусор), «сайт холдинга» в подписи источника,
     неличные номера уходят в «остальные», блок «Холдинг» в карточке, продукция и мощности.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
T = os.path.join(APP, 'templates')
DATA = os.path.join(KOREN, 'data')
KAT = os.path.join(DATA, 'meyer_baza1.db')
SALES = os.path.join(DATA, 'centro_sales_meyer1.db')
BITRIX = os.path.join(DATA, 'bitrix_kc_inn.json')
JSON_PUT = r'C:\seostat\drop\drop-storage\meyer-baza2.json'
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
METKA_FAJL = os.path.join(KOREN, '_bekap', 'baza2-poslednyaya.txt')

POYASA = [
    (2, ('калининград',)), (12, ('камчат', 'чукот')), (11, ('магадан', 'сахалин')),
    (10, ('хабаровск', 'приморск', 'владивосток', 'еврейск')),
    (9, ('забайкаль', 'чита', 'читин', 'амурск', 'якут', 'саха')), (8, ('иркут', 'бурят')),
    (7, ('новосиб', 'томск', 'кемеров', 'кузбас', 'алтай', 'краснояр', 'хакас', 'тыва')), (6, ('омск',)),
    (5, ('башкорт', 'уфа', 'оренбург', 'перм', 'свердлов', 'екатеринбург', 'челябин', 'курган',
         'тюмен', 'ханты', 'югра', 'ямал')),
    (4, ('самар', 'саратов', 'ульянов', 'астрахан', 'удмурт', 'ижевск')),
]
EVROPA = ('москв', 'москов', 'петербург', 'ленинград', 'владимир', 'волгоград', 'вологод', 'воронеж',
          'киров', 'костром', 'краснодар', 'курск', 'нижегород', 'рязан', 'тамбов', 'туль', 'ярослав',
          'калмык', 'крым', 'севастопол', 'татарстан', 'ставропол', 'твер', 'пенз', 'мордов', 'чуваш',
          'марий', 'белгород', 'брянск', 'калуж', 'липец', 'орлов', 'смолен', 'иванов', 'мурман', 'карел',
          'коми', 'архангел', 'ненец', 'новгород', 'псков', 'ростов', 'адыге', 'дагестан', 'ингуш',
          'кабардин', 'карачаев', 'осетия', 'чечен',
          # База 6: новые регионы и города вместо региона – все по Москве
          'запорож', 'донецк', 'луганск', 'херсон', 'чебоксар', 'мамадыш', 'сурск', 'кондрово',
          'старица', 'иванково')


def s_nachala(slovo, tekst):
    return re.search(r'(?<![а-яё])' + re.escape(slovo), tekst) is not None


def poyas(region):
    r = (region or '').casefold()
    for smeshch, slova in POYASA:
        if any(s_nachala(sl, r) for sl in slova):
            return smeshch, 'по региону'
    if not r:
        return 3, 'по Москве: регион не указан'
    if any(s_nachala(sl, r) for sl in EVROPA):
        return 3, 'по региону'
    return 3, 'по Москве: регион не распознан'


def cif10(v):
    d = re.sub(r'\D', '', re.split(r'доб', str(v or ''), flags=re.I)[0])
    return d[-10:] if len(d) >= 10 else ''


# ====================================================================== ПОСТРОЕНИЕ (venv)
if '--postroit' in sys.argv:
    BEKAP = sys.argv[sys.argv.index('--postroit') + 1]
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    logging.disable(logging.CRITICAL)
    from app.services import centro_sales as sales
    assert os.path.normcase(os.environ.get('CENTRO_DB', '')) == os.path.normcase(KAT), os.environ.get('CENTRO_DB')
    assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)

    d = json.load(io.open(JSON_PUT, encoding='utf-8'))
    # ---------- 0. бэкапы баз (backup API: безопасно при работающей панели) и снимок
    for p in (KAT, SALES):
        src = sqlite3.connect(p)
        dst = sqlite3.connect(os.path.join(BEKAP, os.path.basename(p)))
        src.backup(dst)
        dst.close()
        src.close()
    s = sqlite3.connect(SALES)
    s.row_factory = sqlite3.Row
    snimok = {'naznacheniya': {r['inn']: [r['username'], r['assignment_score']] for r in
                               s.execute('select inn, username, assignment_score from company_assignment')},
              'sostoyaniya': [list(r) for r in s.execute('select * from company_state order by inn, username')],
              'zhurnal': s.execute('select count(*) from activity_log').fetchone()[0]}
    io.open(os.path.join(BEKAP, 'snimok-do.json'), 'w', encoding='utf-8').write(json.dumps(snimok, ensure_ascii=False))

    k = sqlite3.connect(KAT)
    k.row_factory = sqlite3.Row
    v_kataloge = {r[0] for r in k.execute('select inn from company')}
    novye = [c for c in d['kompanii'] if not c['sliyanie'] and c['inn'] not in v_kataloge]
    sliyanie = [c for c in d['kompanii'] if c['sliyanie'] or c['inn'] in v_kataloge]
    if any(c['inn'] in snimok['naznacheniya'] for c in novye):
        raise SystemExit('ОСТАНОВКА: у новых ИНН уже есть назначения – Базу 2 уже заливали?')
    bitrix = json.load(io.open(BITRIX, encoding='utf-8'))

    def bitrix_pole(c):
        x = bitrix.get(c['inn'])
        if x:
            return x['sdelok'], 'сделок %d: %s' % (x['sdelok'], ', '.join(
                '%s ×%d' % (v, n) for v, n in sorted(x['voronki'].items(), key=lambda p: -p[1])))
        if c.get('bitrix_fajl'):
            m = re.search(r'(\d+)\s*сдел', c['bitrix_fajl'])
            return (int(m.group(1)) if m else 1), 'по файлу 6: ' + c['bitrix_fajl']
        return 0, None

    kont_po = {}
    for x in d['kontakty']:
        kont_po.setdefault(x['inn'], []).append(x)

    def gotovaya(c):
        z = dict(c)
        ks = kont_po.get(c['inn'], [])
        z['has_purchaser'] = int(c['n_purchaser'] > 0)
        z['has_tech'] = int(c['n_tech'] > 0)
        z['n_signals'] = 0
        z['n_facts'] = 0
        z['bazy'] = d['baza']
        z['bazy_opisanie'] = d['baza_opisanie']
        z['bitrix_kc'], z['bitrix_kc_info'] = bitrix_pole(c)
        z['chas_poyas'], z['chas_poyas_kak'] = poyas(c['region'])
        z['search_blob'] = ' '.join(str(v) for v in (
            c['inn'], c['predpriyatie'], c['region'], c['okvedy_vse'], c['segment'], c['opisanie'],
            c['produkciya'], c['holding'], c['sayt'], c['lpr_kratko'],
            ' '.join('%s %s %s %s' % (x['person'] or '', x['position'], x['role'], x['cifry']) for x in ks)) if v).lower()
        return z

    # ---------- 1. балл и раздача (назначения – ПЕРВЫМИ)
    gotovye = [gotovaya(c) for c in novye]
    for z in gotovye:
        z['_ball'] = sales.company_score(z)
    gruppy = d['gruppy']
    chleny_gruppy = {ch['inn']: gid for gid, g in gruppy.items() for ch in g['chleny']}
    edinicy = {}
    for z in gotovye:
        edinicy.setdefault(z['holding_gruppa'] or ('one-' + z['inn']), []).append(z)
    prinuditelno = {}
    for gid, g in gruppy.items():
        for ch in g['chleny']:
            u = (snimok['naznacheniya'].get(ch['inn']) or [None])[0]
            if u in PRODAVCY:
                prinuditelno[gid] = u
    zagruzka = {p: [0, 0.0] for p in PRODAVCY}
    kuda = {}
    for klyuch, chleny in sorted(edinicy.items(), key=lambda kv: (-max(z['_ball'] for z in kv[1]), kv[0])):
        u = prinuditelno.get(klyuch) or min(PRODAVCY, key=lambda p: (zagruzka[p][0], zagruzka[p][1], p))
        for z in chleny:
            kuda[z['inn']] = u
            zagruzka[u][0] += 1
            zagruzka[u][1] += z['_ball']
    kol_a = [r[1] for r in s.execute('PRAGMA table_info(company_assignment)')]
    seychas = sales.utcnow()
    try:
        for z in gotovye:
            a = {'inn': z['inn'], 'username': kuda[z['inn']], 'assignment_score': z['_ball'],
                 'has_phone': z['has_phone'], 'has_purchaser': z['has_purchaser'], 'has_tech': z['has_tech'],
                 'has_signal': 0, 'assigned_at': seychas, 'source_version': 'meyer-baza2',
                 'assigned_by': 'База 2: поровну по баллу, холдинг одному продавцу'}
            a = {kk: v for kk, v in a.items() if kk in kol_a}
            s.execute('INSERT INTO company_assignment (%s) VALUES (%s)' % (','.join(a), ','.join('?' * len(a))),
                      list(a.values()))
        s.commit()
    except Exception:
        s.rollback()
        raise
    print('назначения: записано %d' % len(gotovye))

    # ---------- 2. каталог одной транзакцией
    try:
        kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
        for imya in ('produkciya', 'moshchnosti', 'holding', 'holding_gruppa', 'v_fajlah_meyer', 'razdel_kc',
                     'kachestvo_nomera', 'sayt_chey', 'otkuda_kompaniya'):
            if imya not in kol:
                k.execute('ALTER TABLE company ADD COLUMN %s TEXT' % imya)
        if 'fragment' not in {r[1] for r in k.execute('PRAGMA table_info(contact)')}:
            k.execute('ALTER TABLE contact ADD COLUMN fragment TEXT')
        k.execute('CREATE TABLE IF NOT EXISTS holding_chlen (gruppa TEXT, inn TEXT, nazvanie TEXT, region TEXT, '
                  'segment TEXT, vyruchka_rub REAL, v_vybore INTEGER, svyaz TEXT)')
        k.execute('CREATE INDEX IF NOT EXISTS ix_holding_chlen ON holding_chlen(gruppa)')
        kol_company = [r[1] for r in k.execute('PRAGMA table_info(company)')]

        def vstavit_kontakt(x):
            k.execute('INSERT INTO contact (inn, value, kind, person, role, position, phone_type, source, source_url, '
                      'is_purchaser, is_tech, has_role, is_unknown_owner, nomer_ne_lichnyy, fragment) '
                      'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)',
                      (x['inn'], x['value'], 'phone', x['person'], x['role'], x['position'], x['phone_type'],
                       x['source'], x['source_url'], x['is_purchaser'], x['is_tech'], x['has_role'],
                       x['nomer_ne_lichnyy'], x['fragment']))
            if x['person']:
                k.execute('INSERT INTO person (inn, person, position, role, phone, phone_type, source_url, source, '
                          'is_tech) VALUES (?,?,?,?,?,?,?,?,?)',
                          (x['inn'], x['person'], x['position'], x['role'], x['value'], x['phone_type'],
                           x['source_url'], x['source'], x['is_tech']))
            if x['lpr'] and x['source_url']:
                k.execute('INSERT INTO company_source (inn, field_name, source, source_url) VALUES (?,?,?,?)',
                          (x['inn'], 'ЛПР: %s' % (x['position'] or x['role']), x['source'].split(' · ')[0],
                           x['source_url']))
        n_k = 0
        for z in gotovye:
            zz = {kk: v for kk, v in z.items() if kk in kol_company}
            k.execute('INSERT INTO company (%s) VALUES (%s)' % (
                ','.join('"%s"' % kk for kk in zz), ','.join('?' * len(zz))), list(zz.values()))
            for x in kont_po.get(z['inn'], []):
                vstavit_kontakt(x)
                n_k += 1
        # слияние с Базой 1: метка, новые номера, пустые поля
        n_sl = 0
        for c in sliyanie:
            st = dict(k.execute('select * from company where inn=?', (c['inn'],)).fetchone())
            bazy = [b.strip() for b in (st.get('bazy') or '').split('|') if b.strip()]
            opis = [o.strip() for o in (st.get('bazy_opisanie') or '').split('|')]
            if d['baza'] not in bazy:
                opis = (opis + [''] * len(bazy))[:len(bazy)]
                bazy.append(d['baza'])
                opis.append(d['baza_opisanie'])
            obnov = {'bazy': ' | '.join(bazy), 'bazy_opisanie': ' | '.join(opis)}
            for pole in ('opisanie', 'produkciya', 'moshchnosti', 'holding', 'holding_gruppa', 'kachestvo_nomera',
                         'v_fajlah_meyer', 'razdel_kc', 'sayt_chey', 'otkuda_kompaniya', 'sayt'):
                if pole in kol_company and not st.get(pole) and c.get(pole):
                    obnov[pole] = c[pole]
            est = {cif10(r[0]) for r in k.execute('select value from contact where inn=?', (c['inn'],))}
            for x in kont_po.get(c['inn'], []):
                if cif10(x['value']) not in est:
                    vstavit_kontakt(x)
                    est.add(cif10(x['value']))
                    n_sl += 1
            roli = [r.strip() for r in (st.get('lpr_roli') or '').split(',') if r.strip()]
            for r in (c.get('lpr_roli') or '').split(','):
                if r.strip() and r.strip() not in roli:
                    roli.append(r.strip())
            obnov['lpr_roli'] = ', '.join(roli)
            k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % kk for kk in obnov),
                      list(obnov.values()) + [c['inn']])
        k.execute("UPDATE company SET lpr_mobilnyy = CASE WHEN EXISTS (SELECT 1 FROM contact ct WHERE ct.inn=company.inn "
                  "AND ct.phone_type='мобильный' AND COALESCE(ct.nomer_ne_lichnyy,'')='' AND COALESCE(ct.has_role,0)=1) "
                  "THEN 1 ELSE 0 END WHERE inn IN (%s)" % ','.join('?' * len(sliyanie)), [c['inn'] for c in sliyanie])
        k.execute("UPDATE company SET n_phones=(SELECT COUNT(*) FROM contact ct WHERE ct.inn=company.inn) "
                  "WHERE inn IN (%s)" % ','.join('?' * len(sliyanie)), [c['inn'] for c in sliyanie])
        # состав холдингов – всем членам групп, где есть хоть одна отобранная
        k.execute('DELETE FROM holding_chlen WHERE gruppa IN (%s)' % ','.join('?' * len(gruppy)), list(gruppy))
        for gid, g in gruppy.items():
            for ch in g['chleny']:
                k.execute('INSERT INTO holding_chlen VALUES (?,?,?,?,?,?,?,?)',
                          (gid, ch['inn'], ch['nazvanie'], ch['region'], ch['segment'], ch['vyruchka_rub'],
                           int(ch['v_vybore']), ch['svyaz']))
        # люди из листа «Люди»: ФИО на живой странице; телефон рядом – из таблицы CC
        n_l = 0
        for p in d.get('lyudi', []):
            if not k.execute('select 1 from person where inn=? and person=?', (p['inn'], p['person'])).fetchone():
                k.execute('INSERT INTO person (inn, person, position, role, phone, phone_type, source_url, source, '
                          'is_tech) VALUES (?,?,?,?,?,?,?,?,0)',
                          (p['inn'], p['person'], p['position'], '', p['phone'], None, p['source_url'], p['source']))
                n_l += 1
        print('люди из листа «Люди»: добавлено %d' % n_l)
        for kk, v in {'baza2_fajl': d['fajl'], 'baza2_zalito': time.strftime('%Y-%m-%d %H:%M'),
                      'baza2_kompaniy_novyh': str(len(gotovye)), 'baza2_sliyanie': str(len(sliyanie)),
                      'baza2_kontaktov': str(n_k + n_sl),
                      'version': 'meyer-baza1+6+4+2-' + time.strftime('%Y%m%d%H%M')}.items():
            k.execute('INSERT OR REPLACE INTO import_info (key, value) VALUES (?,?)', (kk, v))
        k.commit()
    except Exception:
        k.rollback()
        s.execute('DELETE FROM company_assignment WHERE source_version=? AND inn IN (%s)' % ','.join('?' * len(gotovye)),
                  ['meyer-baza2'] + [z['inn'] for z in gotovye])
        s.commit()
        print('ОШИБКА КАТАЛОГА – каталог откатан, назначения Базы 2 удалены')
        raise
    print('каталог: новых компаний %d, их номеров %d; слияние с Базой 1: %d компаний, новых номеров %d' % (
        len(gotovye), n_k, len(sliyanie), n_sl))
    print('всего в каталоге: компаний %d, номеров %d, людей %d, групп-холдингов %d' % (
        k.execute('select count(*) from company').fetchone()[0], k.execute('select count(*) from contact').fetchone()[0],
        k.execute('select count(*) from person').fetchone()[0], len(gruppy)))
    print('битрикс у новых: %d (по справочнику %d, по файлу 6 %d); пояс «не распознан» %d' % (
        sum(1 for z in gotovye if z['bitrix_kc']), sum(1 for z in gotovye if z['inn'] in bitrix),
        sum(1 for z in gotovye if z['bitrix_kc'] and z['inn'] not in bitrix),
        sum(1 for z in gotovye if 'не распознан' in z['chas_poyas_kak'])))
    imena = {r[0]: r[1] for r in s.execute("select username, coalesce(fio,'') from users")}
    vse = sorted(gotovye, key=lambda z: -z['_ball'])
    verh = {z['inn'] for z in vse[:len(vse) // 4]}
    print()
    print('РАЗДАЧА Базы 2 (поровну по баллу, холдинг – одному):')
    for p in PRODAVCY:
        b = [z['_ball'] for z in gotovye if kuda[z['inn']] == p]
        print('   %-18s компаний %3d, средний балл %5.1f, из верхней четверти %2d, ЛПР %3d, через коммутатор %3d' % (
            imena.get(p) or p, len(b), sum(b) / max(1, len(b)),
            sum(1 for z in gotovye if kuda[z['inn']] == p and z['inn'] in verh),
            sum(1 for z in gotovye if kuda[z['inn']] == p and z['kachestvo_nomera'].startswith('ЛПР')),
            sum(1 for z in gotovye if kuda[z['inn']] == p and not z['kachestvo_nomera'].startswith('ЛПР'))))
    print('   принудительно к продавцу Базы 1 (холдинг): %s' % (prinuditelno or 'нет'))
    k.close()
    s.close()
    raise SystemExit(0)

# ====================================================================== ПРОВЕРКА (venv)
if '--proverka' in sys.argv:
    BEKAP = sys.argv[sys.argv.index('--proverka') + 1]
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as cat
    from app import web
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    d = json.load(io.open(JSON_PUT, encoding='utf-8'))
    snimok = json.load(io.open(os.path.join(BEKAP, 'snimok-do.json'), encoding='utf-8'))
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
    b6 = {r[0] for r in k.execute("select inn from company where bazy like '%База 2%'")}
    proverit(b6 == {c['inn'] for c in d['kompanii']}, 'в каталоге с меткой «База 2»: %d = в файле отбора %d' % (len(b6), len(d['kompanii'])))
    vse_inn = {r[0] for r in k.execute('select inn from company')}
    naz = {r[0]: r[1] for r in s.execute('select inn, username from company_assignment')}
    proverit(not (vse_inn - set(naz)), 'у каждой компании каталога есть продавец (без продавца: %d)' % len(vse_inn - set(naz)))
    izm = [inn for inn, (u, sc) in snimok['naznacheniya'].items() if naz.get(inn) != u]
    proverit(not izm, 'назначения Базы 1 не изменились (изменено: %d)' % len(izm))
    sost = [list(r) for r in s.execute('select * from company_state order by inn, username')]
    proverit(len(sost) >= len(snimok['sostoyaniya']) and all(r in sost for r in snimok['sostoyaniya']),
             'статусы продавцов на месте: было %d, есть %d' % (len(snimok['sostoyaniya']), len(sost)))
    # холдинги у одного продавца
    razn = []
    for gid, g in d['gruppy'].items():
        u = {naz.get(ch['inn']) for ch in g['chleny'] if ch['inn'] in vse_inn}
        if len(u) > 1:
            razn.append((g['nazvanie'] or gid, u))
    proverit(not razn, 'каждый холдинг – у одного продавца (%d групп; разные: %s)' % (len(d['gruppy']), razn))
    po = {}
    for c in d['kompanii']:
        if not c['sliyanie'] and c['inn'] not in snimok['naznacheniya']:
            po[naz.get(c['inn'])] = po.get(naz.get(c['inn']), 0) + 1
    print('      новые Базы 2 по продавцам: %s' % po)
    proverit(max(po.values()) - min(po.values()) <= 6, 'раздача ровная (разница не больше размера холдинга)')
    # добавочный номер
    o, dob = cat._razdelit_dobavochnyy('+7 495 000-00-00 доб. 212')
    proverit((o, dob) == ('+7 495 000-00-00', '212') and cat.contact_href('phone', '+7 495 000-00-00 доб. 212') == 'tel:+74950000000,212',
             'добавочный: %r -> %s' % ((o, dob), cat.contact_href('phone', '+7 495 000-00-00 доб. 212')))
    proverit(cat._phone_key('+7 495 000-00-00 доб. 212') == '4950000000', 'ключ номера без добавочного: %s' % cat._phone_key('+7 495 000-00-00 доб. 212'))
    proverit(web._vid_istochnika('https://sibagrogroup.ru/c', 'сайт холдинга (агент) · …', 'argo.ru')['podpis'] == 'сайт холдинга · sibagrogroup.ru',
             'подпись «сайт холдинга»')

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}

    def chislo_strok(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1
    obrab = {r[0] for r in s.execute("select inn from company_state where call_result in ('v_rabote','ne_ponravilas','dubl')")}
    with TestClient(vnutr) as kl:
        n = chislo_strok(kl.get(PUT + '/centro', params={'baza': 'База 2'}).text)
        proverit(n == len(b6 - obrab), 'фильтр «Источник базы: База 2» в «Всей очереди»: %d (ждём %d)' % (n, len(b6 - obrab)))
        n = chislo_strok(kl.get(PUT + '/centro').text)
        proverit(n == len(vse_inn - obrab), '«Вся очередь» у директора: %d (ждём %d)' % (n, len(vse_inn - obrab)))
        t = kl.get(PUT + '/centro').text
        proverit('База 2' in t, 'в списке видна метка «База 2»')
        # карточки: ЛПР с добавочным, коммутатор, холдинг, слияние
        primery = {
            'добавочный': next((c['inn'] for c in d['kompanii'] if not c['sliyanie'] and any(
                'доб.' in x['value'] and x['lpr'] for x in d['kontakty'] if x['inn'] == c['inn'])), None),
            'новая': next(c['inn'] for c in d['kompanii'] if not c['sliyanie']),
            'слияние': next(c['inn'] for c in d['kompanii'] if c['sliyanie']),
        }
        primery = {kk: v for kk, v in primery.items() if v}
        for chto, inn in primery.items():
            cs = '&call_status=' + {r[0]: r[1] for r in s.execute('select inn, call_result from company_state')}.get(inn, '') \
                if inn in obrab else ''
            o = kl.get(PUT + '/centro?inn=' + inn + cs)
            t = o.text
            io.open(os.path.join(DROP, 'centro2-b6-karta-%s.html' % inn), 'w', encoding='utf-8').write(t)
            if chto == 'добавочный':
                ok = o.status_code == 200 and re.search(r'href="tel:\+7\d{10},\d+"', t) and ' доб. ' in t
            elif chto == 'коммутатор':
                # верхний блок контактов – до первой свёртки «остальных» в разделе контактов
                i = t.find('contacts-section')
                j = t.find('<details', i)
                verh = t[i:j] if i >= 0 and j > i else ''
                ok = o.status_code == 200 and 'contact-card' in verh
            elif chto == 'холдинг':
                ok = o.status_code == 200 and 'kholding-section' in t
            elif chto == 'новая':
                ok = o.status_code == 200 and 'База 2' in t
            else:
                ok = o.status_code == 200 and 'База 2' in t and any(b in t for b in ('База 1', 'База 4', 'База 6'))
            proverit(bool(ok), 'карточка «%s» (%s): %s' % (chto, inn, o.status_code))
        st = kl.get(PUT + '/centro/stats')
        proverit(st.status_code == 200, 'статистика: %s' % st.status_code)
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    with TestClient(vnutr) as kl:
        ozh = sum(1 for inn, u in naz.items() if u == 'meyer2' and inn in vse_inn and inn not in obrab)
        n = chislo_strok(kl.get(PUT + '/centro').text)
        proverit(n == ozh, 'продавец meyer2 видит свою очередь: %d (ждём %d)' % (n, ozh))
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ====================================================================== ОСНОВНОЙ ХОД (системный питон)
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('baza2-%Y%m%d-%H%M%S'))
os.makedirs(BEKAP, exist_ok=True)
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
r = subprocess.run([VENV, os.path.abspath(__file__), '--postroit', BEKAP], capture_output=True,
                   timeout=900, cwd=KOREN, env=sreda)
print('===== ПОСТРОЕНИЕ =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
    print('\nПОСТРОЕНИЕ НЕ УДАЛОСЬ – код панели не трогаю')
    raise SystemExit(1)
io.open(METKA_FAJL, 'w', encoding='utf-8').write(BEKAP)

nado = sdelano = 0
log = []


def pravka(p, staro, novo, imya, priznak):
    global nado, sdelano
    nado += 1
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    if t.count(staro) != 1:
        log.append('[ЯКОРЬ: %d] %s – не правлю' % (t.count(staro), imya))
        return
    b = os.path.join(BEKAP, 'kod-' + os.path.basename(p))
    if not os.path.exists(b):
        shutil.copy2(p, b)
    io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    sdelano += 1
    log.append('[ок] ' + imya)


CAT = os.path.join(APP, 'services', 'centro_catalog.py')
pravka(CAT, '''    d = re.sub(r"\\D", "", str(raw or ""))
    return d[-10:] if len(d) >= 10 else ""''', '''    # добавочный не часть номера: «… доб. 212» иначе давал ключ из хвоста с добавочным
    d = re.sub(r"\\D", "", _bez_dobavochnogo(raw))
    return d[-10:] if len(d) >= 10 else ""''', 'каталог: ключ номера без добавочного', '_bez_dobavochnogo(raw))')
pravka(CAT, '''        normalized = normalize_phone(value)
        return "tel:" + normalized if normalized else ""''', '''        osn, dob = _razdelit_dobavochnyy(value)
        normalized = normalize_phone(osn)
        # «tel:+7…,212» – телефон наберёт номер, подождёт и наберёт добавочный
        return ("tel:" + normalized + ("," + dob if dob else "")) if normalized else ""''',
       'каталог: tel:-ссылка с добавочным', 'osn, dob = _razdelit_dobavochnyy(value)\n        normalized')
pravka(CAT, '''        if kind == "phone":
            value = normalize_phone(value) or value
''', '''        if kind == "phone":
            # добавочный сохраняется в показе: раньше «+7 495 000-00-00 доб. 212»
            # превращалось в «+74950000000212», и продавец добавочного не видел
            osn, dob = _razdelit_dobavochnyy(value)
            value = (normalize_phone(osn) or osn) + (" доб. " + dob if dob else "")
''', 'каталог: показ номера с добавочным', 'value = (normalize_phone(osn) or osn) + (" доб. "')
# Окончательный вид правила (после panel_baza6_verh.py): решает ПОСЛЕ цикла, есть ли наверху
# ЛПР или приёмная. Признак – est_verh: повторный прогон не вставит правило второй раз.
pravka(CAT, '''        result.append(item)
    return result''', '''        result.append(item)
    # Неличный номер (продажи, бухгалтерия, общий…) уходит в «остальные», только если
    # наверху есть кому звонить (ЛПР или приёмная). У компании без них любой номер –
    # путь к ЛПР: тогда все наверху, каждый с пометкой вида.
    def _nelichnyy(x):
        return bool(str(x.get("nomer_ne_lichnyy") or "").strip())
    est_verh = any(x["has_role"] and not _nelichnyy(x) for x in result)
    for x in result:
        if _nelichnyy(x):
            x["has_role"] = 0 if est_verh else 1
    return result''', 'каталог: неличные номера – в «остальные», если наверху есть кому звонить', 'est_verh = any(')
nado += 1
t = io.open(CAT, encoding='utf-8').read()
if 'def _razdelit_dobavochnyy' in t:
    sdelano += 1
    log.append('[уже] каталог: разбор добавочного')
else:
    shutil.copy2(CAT, os.path.join(BEKAP, 'kod-centro_catalog-0.py'))
    io.open(CAT, 'w', encoding='utf-8').write(t.rstrip('\n') + r'''


# Добавочный номер (База 6: 131 номер «… доб. NNN»). Отделяется от основного, чтобы
# основной нормализовался и сравнивался по 10 цифрам, а добавочный не терялся.
_ДОБАВОЧНЫЙ = re.compile(r"\s*(?:доб\.?|доп\.?|вн\.?|ext\.?|#)\s*(\d{1,6})\s*$", re.I)


def _razdelit_dobavochnyy(raw) -> tuple[str, str]:
    """«+7 495 000-00-00 доб. 212» -> («+7 495 000-00-00», «212»); без добавочного – (raw, "")."""
    t = str(raw or "").strip()
    m = _ДОБАВОЧНЫЙ.search(t)
    if not m:
        return t, ""
    return t[:m.start()].strip(), m.group(1)


def _bez_dobavochnogo(raw) -> str:
    return _razdelit_dobavochnyy(raw)[0]
''')
    sdelano += 1
    log.append('[ок] каталог: разбор добавочного')

WEB = os.path.join(APP, 'web.py')
pravka(WEB, '''    dk = _domen(sayt)
    if dk and (d == dk''', '''    if "площадка закупок" in s:
        return {"podpis": "площадка закупок · %s" % pokaz, "vid": "тендерная площадка", "domen": pokaz,
                "zametki": zametki}
    if "сайт холдинга" in s:
        # База 6: номер с сайта холдинга, а не самой компании – не «сторонний», но и не свой
        return {"podpis": "сайт холдинга · %s" % pokaz, "vid": "сайт холдинга", "domen": pokaz,
                "zametki": zametki}
    dk = _domen(sayt)
    if dk and (d == dk''', 'подпись: «сайт холдинга», «площадка закупок»', '"сайт холдинга · %s"')

RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
nado += 1
t = io.open(RCS, encoding='utf-8').read()
if 'def _kholding(' in t:
    sdelano += 1
    log.append('[уже] маршрут: состав холдинга')
else:
    shutil.copy2(RCS, os.path.join(BEKAP, 'kod-routes_centro_sales-0.py'))
    io.open(RCS, 'w', encoding='utf-8').write(t.rstrip('\n') + r'''


# Состав холдинга для карточки (владелец 08.10: «для холдингов сделать свою структуру в
# карточке»). Группа – общий номер у разных ИНН или одно название холдинга; собрана при
# заливке Базы 6 по всему файлу, поэтому в списке есть и компании, которых в панели нет.
def _kholding(chosen, assignments, states, user):
    gruppa = str(chosen.get("holding_gruppa") or "")
    if not gruppa:
        return None
    try:
        kc = catalog.connect()
        try:
            chleny = [dict(r) for r in kc.execute(
                "SELECT * FROM holding_chlen WHERE gruppa=? ORDER BY vyruchka_rub DESC", (gruppa,))]
            v_paneli = {str(r[0]) for r in kc.execute(
                "SELECT inn FROM company WHERE inn IN (%s)" % ",".join("?" * len(chleny)),
                [c["inn"] for c in chleny])} if chleny else set()
        finally:
            kc.close()
    except Exception:  # noqa: BLE001 – нет таблицы (база без холдингов): блока нет
        return None
    for c in chleny:
        c["eto_ona"] = c["inn"] == chosen["inn"]
        c["v_paneli"] = c["inn"] in v_paneli
        a = assignments.get(c["inn"])
        c["prodavec"] = a["username"] if a else ""
        c["url"] = ""
        if c["v_paneli"] and not c["eto_ona"] and a and (
                user["role"] == "admin" or a["username"] == user["username"]):
            rez = (states.get((c["inn"], a["username"])) or {}).get("call_result") or ""
            c["url"] = "%s/centro?%s" % (BP, urlencode(dict(
                {"inn": c["inn"]}, **({"call_status": rez} if rez in sales.CALL_RESULT_CHOICES else {}))))
    return {"nazvanie": str(chosen.get("holding") or ""), "chleny": chleny}
''')
    sdelano += 1
    log.append('[ок] маршрут: состав холдинга')
pravka(RCS, '''    company_sources: list[dict] = []
    if chosen and not error:''', '''    company_sources: list[dict] = []
    kholding = None
    if chosen and not error:''', 'маршрут: kholding по умолчанию', '    kholding = None\n    if chosen and not error:')
pravka(RCS, '''            company_sources = catalog.company_sources(chosen["inn"])
''', '''            company_sources = catalog.company_sources(chosen["inn"])
            kholding = _kholding(chosen, assignments, states, user)
''', 'маршрут: состав холдинга в карточку', 'kholding = _kholding(chosen, assignments, states, user)')
pravka(RCS, '''            "company_sources": company_sources,
''', '''            "company_sources": company_sources,
            "kholding": kholding,
''', 'маршрут: kholding в шаблон', '"kholding": kholding,')

C = os.path.join(T, 'centro.html')
pravka(C, "{% macro source_link(source, url, label='Источник', telefon=False) %}",
       "{% macro source_link(source, url, label='Источник', telefon=False, fragment='') %}",
       'карточка: фрагмент страницы в подсказке (параметр)', "telefon=False, fragment='') %}")
pravka(C, '''  <div class="source-line" title="{{ source or '' }}">''',
       '''  <div class="source-line" title="{{ source or '' }}{% if fragment %}&#10;На странице: «{{ fragment }}»{% endif %}">''',
       'карточка: фрагмент страницы в подсказке', 'На странице: «{{ fragment }}»')
pravka(C, '{{ source_link(contact.source, contact.source_url, telefon=True) }}',
       "{{ source_link(contact.source, contact.source_url, telefon=True, fragment=contact.fragment or '') }}",
       'карточка: фрагмент у номера', "fragment=contact.fragment or ''")
pravka(C, '{% if contact.phone_type %}<span class="tag">{{ contact.phone_type }}</span>{% endif %}',
       '{% if contact.phone_type %}<span class="tag">{{ contact.phone_type }}</span>{% endif %}'
       '{% if contact.nomer_ne_lichnyy %}<span class="tag tag-ne-lpr" title="Не ЛПР: путь к ЛПР через этот номер">'
       '{{ contact.nomer_ne_lichnyy }}</span>{% endif %}', 'карточка: вид неличного номера', 'tag-ne-lpr')
pravka(C, '''{% if company.opisanie %}<p class="opisanie" style="max-width:900px">{{ company.opisanie }}</p>{% endif %}''',
       '''{% if company.opisanie %}<p class="opisanie" style="max-width:900px">{{ company.opisanie }}</p>{% endif %}'''
       '''{% if company.produkciya %}<p class="opis-dop"><b>Продукция:</b> {{ company.produkciya }}</p>{% endif %}'''
       '''{% if company.moshchnosti %}<p class="opis-dop"><b>Мощности:</b> {{ company.moshchnosti }}</p>{% endif %}''',
       'карточка: продукция и мощности', 'class="opis-dop"><b>Продукция:</b>')
pravka(C, '''{% if company.popadanie %}<span><b>Попадание</b> {{ company.popadanie }}</span>{% endif %}''',
       '''{% if company.popadanie %}<span><b>Попадание</b> {{ company.popadanie }}</span>{% endif %}'''
       '''{% if company.holding %}<span><b>Холдинг</b> {{ company.holding }}</span>{% endif %}''',
       'карточка: холдинг в шапке', '<span><b>Холдинг</b> {{ company.holding }}</span>')
pravka(C, '''  {% if people %}
''', '''  {% if kholding and kholding.chleny %}
  {# Холдинг (владелец 08.10): компании одной группы – по общему номеру или названию
     холдинга. Вся группа у одного продавца, чтобы двое не звонили одному человеку. #}
  <section class="card kholding-section">
    <div class="section-head"><div><h2>Холдинг{% if kholding.nazvanie %}: {{ kholding.nazvanie }}{% endif %}</h2><p>Компании одной группы – по общему номеру или названию холдинга. Вся группа у одного продавца.</p></div><span class="counter">{{ kholding.chleny|length }}</span></div>
    <div style="overflow-x:auto"><table class="kholding-tab">
      <thead><tr><th>Компания</th><th>ИНН</th><th>Регион</th><th>Сегмент</th><th>Выручка</th><th>Чем связана</th><th>В панели</th></tr></thead>
      <tbody>
      {% for m in kholding.chleny %}
        <tr{% if m.eto_ona %} class="eto-ona"{% endif %}>
          <td>{% if m.eto_ona %}<b>{{ m.nazvanie }}</b> <span class="muted">(эта)</span>{% elif m.url %}<a href="{{ m.url }}">{{ m.nazvanie }}</a>{% else %}{{ m.nazvanie }}{% endif %}</td>
          <td>{{ m.inn }}</td><td>{{ m.region or '–' }}</td><td>{{ m.segment or '–' }}</td>
          <td style="white-space:nowrap">{{ money_ru(m.vyruchka_rub) or '–' }}</td><td>{{ m.svyaz or '–' }}</td>
          <td>{% if m.v_paneli %}{{ (m.prodavec|fio) if m.prodavec else 'да' }}{% else %}<span class="muted">нет: без номера ЛПР</span>{% endif %}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table></div>
  </section>
  {% endif %}
  {% if people %}
''', 'карточка: блок «Холдинг»', 'kholding-section')
pravka(C, '.hide-company{margin:8px 0 0;',
       '.opis-dop{margin:4px 0 0;font-size:13px;color:var(--navy);max-width:900px}\n'
       '.tag-ne-lpr{background:#f6f7fb;color:#667085}\n'
       '.kholding-tab{border-collapse:collapse;width:100%;font-size:13px}\n'
       '.kholding-tab th,.kholding-tab td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}\n'
       '.kholding-tab th{color:var(--muted);font-weight:600}\n'
       '.kholding-tab tr.eto-ona td{background:#f4f6fb}\n'
       '.hide-company{margin:8px 0 0;', 'карточка: стили', '.kholding-tab{')
for x in log:
    print('   ' + x)
print('правок кода внесено: %d из %d' % (sdelano, nado))

p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: База 2 %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
import urllib.request
try:
    kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
except Exception as e:  # noqa: BLE001
    kod = str(e)[:80]
print('перезапущено, вход: %s' % kod)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', BEKAP], capture_output=True,
                   timeout=1200, cwd=KOREN, env=sreda)
vyvod = r.stdout.decode('utf-8', 'replace')
if r.returncode:
    vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:]
io.open(os.path.join(DROP, 'centro2-baza2-proverka.txt'), 'w', encoding='utf-8').write(vyvod)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(vyvod[-4000:])
print('бэкап (базы до заливки, снимок, старый код): %s' % BEKAP)
