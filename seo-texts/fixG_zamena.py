# -*- coding: utf-8 -*-
r"""fixG: замена 13 помеченных компаний панели Meyer (владелец 09.10: «выкинь их, добавь из последнего
списка нормальных компаний»).

План (номера телефонов – только в нём) собирает локально fixG_plan.py и кладёт на дроп fixG-plan.json.
Здесь, на сервере, по порядку:
  0. копии обеих баз (backup API) в C:\centro2\_bekap\fixG-<время>\ – НЕ для отката целиком;
  1. сверка с планом: 13 с pometka_ocheredi те же и у тех же продавцов, новых ИНН нет ни в каталоге,
     ни в назначениях; по 13 убираемым НЕТ действий продавцов (company_state, company_comment,
     zvonok_sobytie, activity_log, hidden_item) – иначе остановка, ничего не меняется;
  2. каталог, одна транзакция: строки 13 из company, contact, person, company_source, holding_chlen,
     fact, signal переносятся в arhiv_<таблица> (те же колонки + arhiv_prichina, arhiv_data) и
     удаляются из рабочих (число перенесённых = число удалённых, иначе откат);
  3. продажи, одна транзакция: 13 строк company_assignment -> arhiv_company_assignment и удаление;
     назначения 13 новых (ДО вставки в каталог: иначе панель раздала бы их сама) – каждому продавцу
     столько, сколько он потерял; итог 150 у каждого, иначе откат;
  4. каталог, одна транзакция: 13 компаний «База 3» (реквизиты checko, регион/сегмент/отрасль,
     «чей сайт» – уже в плане), номера, люди (в т. ч. ЛПР без телефона), источники, холдинг
     (gG-…: состав и метка у члена группы из панели); Битрикс КЦ – по справочнику bitrix_kc_inn.json.
     Ошибка – откат каталога, назначения новых удаляются, прежние 13 возвращаются из архива;
  5. флаги ЛПР и lpr_kratko 13 новых – той же функцией, что fixF2_dannye (contacts() панели),
     search_blob; балл очереди – отдельно: fixF2_ball.py --tolko-ball;
  6. журнал на дроп fixG-zhurnal-<время>.json; проверка TestClient на ВРЕМЕННЫХ копиях баз.
Код панели не меняется, перезапуска нет (замок не нужен).

    python3 zapusk_na_servere.py fixG_zamena.py [--suhoy]       # --suhoy: всё на копиях баз
    python3 zapusk_na_servere.py fixG_zamena.py --tolko-proverka
    локально: python3 fixG_zamena.py --lokalno <каталог.db> <продажи.db> <корень с app> <plan.json>
"""
import collections
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
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
BITRIX = os.path.join(KOREN, 'data', 'bitrix_kc_inn.json')
DROP = r'C:\seostat\drop\drop-storage'
PLAN = os.path.join(DROP, 'fixG-plan.json')
PUT = '/obzvon-meyer'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
TABLICY = ('company', 'contact', 'person', 'company_source', 'holding_chlen', 'fact', 'signal')
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')
VREMYA = time.strftime('%Y%m%d-%H%M%S')
METKA_ARHIVA = 'fixG ' + time.strftime('%Y-%m-%d %H:%M:%S')
LOKALNO = '--lokalno' in sys.argv

if not LOKALNO and '--vnutri' not in sys.argv and '--proverka' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1650, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5900:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


def podkl(put):
    k = sqlite3.connect(put, timeout=30)
    k.row_factory = sqlite3.Row
    k.execute('PRAGMA busy_timeout=30000')
    return k


def nachat(k):
    for _ in range(20):
        try:
            k.execute('BEGIN IMMEDIATE')
            return
        except sqlite3.OperationalError:
            time.sleep(3)
    raise SystemExit('база занята')


def zakrep(s, inny):
    out = {}
    for t in DEYSTVIYA:
        try:
            n = s.execute('SELECT inn, COUNT(*) FROM %s WHERE inn IN (%s) GROUP BY inn' % (t, ','.join('?' * len(inny))),
                          list(inny)).fetchall()
        except sqlite3.OperationalError:
            continue
        for inn, c in n:
            out.setdefault(inn, {})[t] = c
    return out


def kolonki(k, t):
    return [r[1] for r in k.execute('PRAGMA table_info(%s)' % t)]


def arhiv_tablica(k, t):
    """arhiv_<t> с теми же колонками + arhiv_prichina, arhiv_data (недостающие колонки добавляются)."""
    kol = kolonki(k, t)
    k.execute('CREATE TABLE IF NOT EXISTS arhiv_%s AS SELECT * FROM %s WHERE 0' % (t, t))
    est = set(kolonki(k, 'arhiv_' + t))
    for c in kol + ['arhiv_prichina', 'arhiv_data']:
        if c not in est:
            k.execute('ALTER TABLE arhiv_%s ADD COLUMN "%s" TEXT' % (t, c))
    return kol


# ====================================================================== флаги ЛПР (копия fixF2_dannye)
def pokaz(cat, v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


def flagi(cat, items):
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    sprosit = [x for x in items if x['kind'] == 'sprosit']
    roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
    fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    if lpr:
        l0 = (fio_mob or mob or lpr)[0]
        kr = ' · '.join(v for v in (l0['person'], l0['position'] or l0['rol_vid'], pokaz(cat, l0['value'])) if v)
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
                  else 'ЛПР не найден, номер с сайта: %s') % pokaz(cat, p0['value'])
            n_mob = sum(1 for x in tel if x['vid_nomera'] == 'мобильный')
            if n_mob:
                kr += ' (мобильных без ЛПР: %d)' % n_mob
        else:
            kr = 'ЛПР не найден' + (', номера только неличные: %d' % len(tel) if tel else ', номеров нет')
    return {'has_tech': int(any(x['is_tech'] for x in lpr)), 'n_tech': sum(1 for x in lpr if x['is_tech']),
            'has_purchaser': int(any(x['is_purchaser'] for x in lpr)), 'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
            'lpr_mobilnyy': int(bool(mob)), 'lpr_s_fio': len(fio_lpr), 'lpr_roli': ', '.join(roli), 'lpr_kratko': kr,
            'n_phones': len(tel), 'has_phone': int(bool(tel))}


def bitrix_razbor(info):     # = fixE1_regiony_segmenty.bitrix
    m = re.match(r'\s*сделок\s+(\d+)\s*:\s*(.*)$', info or '')
    if not m:
        return None, 0
    voronki = {}
    for chast in m.group(2).split(','):
        mm = re.match(r'\s*(.+?)\s*×\s*(\d+)\s*$', chast)
        if mm:
            voronki[mm.group(1)] = voronki.get(mm.group(1), 0) + int(mm.group(2))
    return int(m.group(1)), (1 if any(re.match(r'СЦ\s*[-–—]', v) for v in voronki) else 0)


# ====================================================================== ОСНОВНАЯ РАБОТА
def rabota(KAT, SALES, plan, bitrix, BEKAP, suhoy_metka=''):
    from app.services import centro_catalog as cat
    from app.services import centro_sales as sales
    zh = {'vremya': VREMYA, 'metka_arhiva': METKA_ARHIVA, 'bekap': BEKAP, 'suhoy': bool(suhoy_metka),
          'ubrano': {}, 'naznacheniya_ubrany': [], 'naznacheniya_novye': [], 'vstavleno': {}, 'holding': [],
          'flagi': [], 'oshibki': []}
    ubrat = {u['inn']: u for u in plan['ubrat']}
    novye = {c['inn']: c for c in plan['kompanii']}
    k = podkl(KAT)
    s = podkl(SALES)
    # ---------- 1. сверка
    seychas_pom = {r['inn']: r['pometka_ocheredi'] for r in
                   k.execute("SELECT inn, pometka_ocheredi FROM company WHERE TRIM(COALESCE(pometka_ocheredi,''))<>''")}
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    osh = []
    if set(seychas_pom) != set(ubrat):
        osh.append('помеченные сейчас %s ≠ план %s' % (sorted(seychas_pom), sorted(ubrat)))
    for inn, u in ubrat.items():
        if vlad.get(inn) != u['prodavec']:
            osh.append('%s: продавец сейчас %s, в плане %s' % (inn, vlad.get(inn), u['prodavec']))
    v_kat = {r[0] for r in k.execute('SELECT inn FROM company WHERE inn IN (%s)' % ','.join('?' * len(novye)), list(novye))}
    if v_kat:
        osh.append('новые уже в каталоге: %s' % sorted(v_kat))
    if set(novye) & set(vlad):
        osh.append('у новых уже есть назначения: %s' % sorted(set(novye) & set(vlad)))
    dz = zakrep(s, ubrat)
    if dz:
        osh.append('ПО УБИРАЕМЫМ ЕСТЬ ДЕЙСТВИЯ ПРОДАВЦОВ – не трогаю: %s' % dz)
    if osh:
        print('ОСТАНОВКА, ничего не изменено:\n  ' + '\n  '.join(osh))
        raise SystemExit(4)
    print('сверка: 13 помеченных и продавцы совпали с планом; действий продавцов по ним нет; новых в базе нет')

    # ---------- 2. каталог: архив и удаление 13
    nachat(k)
    try:
        for t in TABLICY:
            kol = arhiv_tablica(k, t)
            spisok_k = ','.join('"%s"' % c for c in kol)
            n_do = k.execute('SELECT COUNT(*) FROM %s WHERE inn IN (%s)' % (t, ','.join('?' * len(ubrat))), list(ubrat)).fetchone()[0]
            n_a = 0
            for inn, u in ubrat.items():
                prich = ('владелец 09.10: «выкинь их, добавь из последнего списка нормальных компаний»; %s; была у %s'
                         % (u['pometka_ocheredi'], u['prodavec']))
                cur = k.execute('INSERT INTO arhiv_%s (%s, arhiv_prichina, arhiv_data) SELECT %s, ?, ? FROM %s WHERE inn=?'
                                % (t, spisok_k, spisok_k, t), (prich, METKA_ARHIVA, inn))
                n_a += cur.rowcount
            stroki = [dict(r) for r in k.execute('SELECT * FROM %s WHERE inn IN (%s)' % (t, ','.join('?' * len(ubrat))), list(ubrat))]
            cur = k.execute('DELETE FROM %s WHERE inn IN (%s)' % (t, ','.join('?' * len(ubrat))), list(ubrat))
            if not (n_do == n_a == cur.rowcount):
                raise RuntimeError('%s: было %d, в архив %d, удалено %d' % (t, n_do, n_a, cur.rowcount))
            zh['ubrano'][t] = stroki
            print('   %-15s в архив и удалено: %d' % (t, n_a))
        if k.execute("SELECT COUNT(*) FROM company WHERE TRIM(COALESCE(pometka_ocheredi,''))<>''").fetchone()[0]:
            raise RuntimeError('после удаления остались компании с пометкой')
        k.commit()
    except BaseException:
        k.rollback()
        raise
    print('каталог: 13 компаний перенесены в arhiv_* и удалены (метка архива «%s»)' % METKA_ARHIVA)

    def vernut_katalog():
        """Аварийно: вернуть 13 из архива этого прогона (если что-то дальше не удалось)."""
        nachat(k)
        for t in TABLICY:
            kol = ','.join('"%s"' % c for c in kolonki(k, t))
            k.execute('INSERT INTO %s (%s) SELECT %s FROM arhiv_%s WHERE arhiv_data=?' % (t, kol, kol, t), (METKA_ARHIVA,))
            k.execute('DELETE FROM arhiv_%s WHERE arhiv_data=?' % t, (METKA_ARHIVA,))
        k.commit()
        print('АВАРИЯ: 13 компаний возвращены в каталог из архива')

    # ---------- 3. продажи: архив назначений 13 и назначения новых (ДО каталога)
    nachat(s)
    try:
        dz = zakrep(s, ubrat)
        if dz:
            raise RuntimeError('за время работы появились действия по убираемым: %s' % dz)
        kol_a = arhiv_tablica(s, 'company_assignment')
        sk = ','.join('"%s"' % c for c in kol_a)
        for inn, u in ubrat.items():
            s.execute('INSERT INTO arhiv_company_assignment (%s, arhiv_prichina, arhiv_data) SELECT %s, ?, ? '
                      'FROM company_assignment WHERE inn=?' % (sk, sk),
                      ('владелец 09.10: «выкинь их»; %s' % u['pometka_ocheredi'], METKA_ARHIVA, inn))
        zh['naznacheniya_ubrany'] = [dict(r) for r in s.execute(
            'SELECT * FROM company_assignment WHERE inn IN (%s)' % ','.join('?' * len(ubrat)), list(ubrat))]
        cur = s.execute('DELETE FROM company_assignment WHERE inn IN (%s)' % ','.join('?' * len(ubrat)), list(ubrat))
        if cur.rowcount != len(ubrat):
            raise RuntimeError('удалено назначений %d из %d' % (cur.rowcount, len(ubrat)))
        seychas = sales.utcnow()
        kol_set = set(kol_a)
        for inn, u in plan['prodavcy'].items():
            st = plan['stupeni'][inn]
            c = novye[inn]
            a = {'inn': inn, 'username': u, 'assignment_score': st['score'], 'has_phone': 1,
                 'has_purchaser': int(c.get('has_purchaser') or 0), 'has_tech': int(c.get('has_tech') or 0), 'has_signal': 0,
                 'assigned_at': seychas, 'source_version': 'meyer-baza3-fixG',
                 'assigned_by': 'База 3, замена помеченных 09.10 (fixG): владелец «выкинь их, добавь из последнего списка»',
                 'stupen_ocheredi': st['tier']}
            a = {kk: v for kk, v in a.items() if kk in kol_set}
            s.execute('INSERT INTO company_assignment (%s) VALUES (%s)' % (','.join(a), ','.join('?' * len(a))), list(a.values()))
            zh['naznacheniya_novye'].append(a)
        sch = collections.Counter(r[0] for r in s.execute('SELECT username FROM company_assignment'))
        if any(sch[p] != 150 for p in PRODAVCY):
            raise RuntimeError('не по 150: %s' % dict(sch))
        s.commit()
    except BaseException:
        s.rollback()
        vernut_katalog()
        raise
    print('продажи: назначения 13 убраны (в arhiv_company_assignment), новые 13 назначены: %s; итог %s' % (
        dict(collections.Counter(plan['prodavcy'].values())), dict(sch)))

    # ---------- 4. каталог: 13 новых
    nachat(k)
    try:
        kc, kk_, kp = set(kolonki(k, 'company')), set(kolonki(k, 'contact')), set(kolonki(k, 'person'))
        for c in ('vyruchka_ishodnaya', 'otrasl', 'proverka_sayta', 'sayt_chey_ishodnyy', 'region_istochnik', 'segment_dop',
                  'segment_osn_ishodnyy', 'popadanie_ishodnoe', 'pometka_ocheredi'):
            if c not in kc:
                raise RuntimeError('в каталоге нет колонки company.%s (ожидалась после правок агентов)' % c)
        zh['vstavleno'] = {'company': [], 'contact': [], 'person': [], 'company_source': [], 'holding_chlen': []}
        for inn, c in novye.items():
            r = dict(c)
            x = bitrix.get(inn)
            if x:
                r['bitrix_kc'] = x['sdelok']
                r['bitrix_kc_info'] = 'сделок %d: %s' % (x['sdelok'], ', '.join(
                    '%s ×%d' % (v, n) for v, n in sorted(x['voronki'].items(), key=lambda p: -p[1])))
                r['bitrix_sdelok'], r['bitrix_klient_sc'] = bitrix_razbor(r['bitrix_kc_info'])
            r = {kk: v for kk, v in r.items() if kk in kc}
            k.execute('INSERT INTO company (%s) VALUES (%s)' % (','.join('"%s"' % x for x in r), ','.join('?' * len(r))),
                      list(r.values()))
            zh['vstavleno']['company'].append(inn)
        for x in plan['kontakty']:
            r = {kk: v for kk, v in x.items() if kk in kk_}
            cur = k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['contact'].append(cur.lastrowid)
        for x in plan['lyudi']:
            r = {kk: v for kk, v in x.items() if kk in kp}
            cur = k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['person'].append(cur.lastrowid)
        for x in plan['istochniki']:
            cur = k.execute('INSERT INTO company_source (inn, field_name, source, source_url) VALUES (?,?,?,?)',
                            (x['inn'], x['field_name'], x['source'], x['source_url']))
            zh['vstavleno']['company_source'].append(cur.lastrowid)
        h = plan.get('holding')
        if h:
            k.execute('DELETE FROM holding_chlen WHERE gruppa=?', (h['gruppa'],))
            for inn in h['chleny']:
                c = k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone()
                if not c:
                    continue
                c = dict(c)
                k.execute('INSERT INTO holding_chlen (gruppa, inn, nazvanie, region, segment, vyruchka_rub, v_vybore, svyaz) '
                          'VALUES (?,?,?,?,?,?,?,?)', (h['gruppa'], inn, c['predpriyatie'], c['region'], c['segment'],
                                                       c['vyruchka_rub'], 1, h['svyaz']))
                zh['vstavleno']['holding_chlen'].append(inn)
                if inn not in novye:
                    star = {'holding': c.get('holding'), 'holding_gruppa': c.get('holding_gruppa')}
                    if (c.get('holding_gruppa') or '') not in ('', h['gruppa']):
                        zh['oshibki'].append('%s уже в группе %s – метку группы не меняю' % (inn, c['holding_gruppa']))
                        continue
                    k.execute('UPDATE company SET holding=?, holding_gruppa=? WHERE inn=?', (h['nazvanie'], h['gruppa'], inn))
                    zh['holding'].append({'inn': inn, 'bylo': star, 'stalo': {'holding': h['nazvanie'], 'holding_gruppa': h['gruppa']}})
        for kk, v in {'fixG_zamena': VREMYA, 'fixG_ubrano': ','.join(sorted(ubrat)), 'fixG_dobavleno': ','.join(sorted(novye))}.items():
            k.execute('INSERT OR REPLACE INTO import_info (key, value) VALUES (?,?)', (kk, v))
        n = k.execute('SELECT COUNT(*) FROM company').fetchone()[0]
        if n != 600:
            raise RuntimeError('в каталоге %d компаний (ждали 600)' % n)
        k.commit()
    except BaseException:
        k.rollback()
        # назначения новых убрать, прежние вернуть, каталог вернуть
        nachat(s)
        s.execute('DELETE FROM company_assignment WHERE source_version=? AND inn IN (%s)' % ','.join('?' * len(novye)),
                  ['meyer-baza3-fixG'] + list(novye))
        kol = ','.join('"%s"' % c for c in kolonki(s, 'company_assignment'))
        s.execute('INSERT INTO company_assignment (%s) SELECT %s FROM arhiv_company_assignment WHERE arhiv_data=?' % (kol, kol),
                  (METKA_ARHIVA,))
        s.execute('DELETE FROM arhiv_company_assignment WHERE arhiv_data=?', (METKA_ARHIVA,))
        s.commit()
        vernut_katalog()
        raise
    print('каталог: 13 новых – компаний %d, номеров %d, людей %d, источников %d, холдинг %s' % (
        len(zh['vstavleno']['company']), len(zh['vstavleno']['contact']), len(zh['vstavleno']['person']),
        len(zh['vstavleno']['company_source']), zh['vstavleno']['holding_chlen']))

    # ---------- 5. флаги ЛПР, lpr_kratko, search_blob – по контактам карточки
    nachat(k)
    try:
        for inn in novye:
            c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            items = cat.contacts(inn)
            nov = flagi(cat, items)
            nov['search_blob'] = ' '.join(str(v) for v in (
                inn, c['predpriyatie'], c['region'], c['okvedy_vse'], c['segment'], c['opisanie'], c.get('produkciya'),
                c.get('holding'), c['sayt'], nov['lpr_kratko'], c.get('adres'), c.get('direktor'),
                ' '.join('%s %s %s %s' % (x.get('person') or '', x.get('position') or '', x.get('rol_vid') or '',
                                          cat._phone_key(x.get('value'))) for x in items if x['kind'] in ('phone', 'sprosit'))) if v).lower()
            izm = {p: v for p, v in nov.items() if c.get(p) != v}
            if izm:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % p for p in izm), list(izm.values()) + [inn])
                zh['flagi'].append({'inn': inn, 'bylo': {p: c.get(p) for p in izm if p != 'search_blob'},
                                    'stalo': {p: v for p, v in izm.items() if p != 'search_blob'}})
        k.commit()
    except BaseException:
        k.rollback()
        raise
    print('флаги ЛПР: обновлены у %d из 13' % len(zh['flagi']))
    for f in zh['flagi']:
        print('   %s: %s' % (f['inn'], re.sub(r'\+7 9\d\d \d{3}-(\d\d)-\d\d', r'+7 9xx xxx-\1-xx', f['stalo'].get('lpr_kratko', ''))[:110]))
    # назначения: балл очереди и ступень – формулой fixF2_ball (та же функция; общий пересчёт всех –
    # отдельным прогоном fixF2_ball.py --tolko-ball), has_* – по флагам
    E2 = None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for imya in ('3s_fixF2_ball', 'fixF2_ball'):
        try:
            E2 = __import__(imya)
            break
        except ImportError:
            continue
    nachat(s)
    for inn in novye:
        c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
        st = plan['stupeni'][inn]
        if E2:
            d = E2.razbor_kompanii(c, cat.contacts(inn), cat, sales)
            st = {'score': d['score'], 'tier': d['tier']}
            if d['tier'] != plan['stupeni'][inn]['tier']:
                zh['oshibki'].append('%s: ступень на сервере %d, в плане %d' % (inn, d['tier'], plan['stupeni'][inn]['tier']))
        s.execute('UPDATE company_assignment SET has_phone=?, has_purchaser=?, has_tech=?, assignment_score=?, stupen_ocheredi=? '
                  'WHERE inn=?', (c['has_phone'], c['has_purchaser'], c['has_tech'], st['score'], st['tier'], inn))
        zh['naznacheniya_novye'].append({'inn': inn, 'ball_ocheredi': st['score'], 'stupen': st['tier']})
    s.commit()
    print('балл очереди новых по формуле: %s' % ('fixF2_ball' if E2 else 'НЕ НАЙДЕНА – оставлен балл плана'))
    if zh['oshibki']:
        print('ВНИМАНИЕ: %s' % zh['oshibki'])
    k.close()
    s.close()
    put = os.path.join(DROP if not LOKALNO else os.path.dirname(os.path.abspath(KAT)),
                       'fixG-zhurnal-%s%s.json' % (VREMYA, suhoy_metka))
    io.open(put, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=1, default=str))
    print('журнал: %s' % put)
    return zh


# ====================================================================== ПРОВЕРКА (venv, копии баз)
def proverka(test_sales, test_kat):
    import html as H
    import warnings
    warnings.filterwarnings('ignore')
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    logging.disable(logging.CRITICAL)
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = test_sales
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = test_kat
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as cat
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plan = json.load(io.open(PLAN, encoding='utf-8'))
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    ok(str(cat.db_path()) == test_kat and str(sales.sales_db_path()) == test_sales, 'базы – временные копии')
    k = sqlite3.connect(test_kat)
    k.row_factory = sqlite3.Row
    s = sqlite3.connect(test_sales)
    s.row_factory = sqlite3.Row
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    score = dict(s.execute('SELECT inn, assignment_score FROM company_assignment').fetchall())
    stup = dict(s.execute('SELECT inn, stupen_ocheredi FROM company_assignment').fetchall())
    vse = {r[0] for r in k.execute('SELECT inn FROM company')}
    sch = collections.Counter(u for i, u in vlad.items() if i in vse)
    ok(all(sch[p] == 150 for p in PRODAVCY) and len(vse) == 600 and set(vlad) == vse,
       'по 150 у каждого продавца: %s; компаний 600: %d; назначения = каталог: %s' % (dict(sch), len(vse), set(vlad) == vse))
    n_pom = k.execute("SELECT COUNT(*) FROM company WHERE TRIM(COALESCE(pometka_ocheredi,''))<>''").fetchone()[0]
    ok(n_pom == 0, 'компаний с pometka_ocheredi в рабочем каталоге: %d' % n_pom)
    ubr = [u['inn'] for u in plan['ubrat']]
    for t in TABLICY:
        n_r = k.execute('SELECT COUNT(*) FROM %s WHERE inn IN (%s)' % (t, ','.join('?' * len(ubr))), ubr).fetchone()[0]
        n_a = k.execute('SELECT COUNT(*) FROM arhiv_%s WHERE inn IN (%s)' % (t, ','.join('?' * len(ubr))), ubr).fetchone()[0]
        ok(n_r == 0, '%s: строк 13 убранных в рабочей %d, в arhiv_%s %d' % (t, n_r, t, n_a))
    n_a = s.execute('SELECT COUNT(*) FROM arhiv_company_assignment WHERE inn IN (%s)' % ','.join('?' * len(ubr)), ubr).fetchone()[0]
    ok(n_a >= 13 and not (set(ubr) & set(vlad)), 'назначения 13 убранных: в arhiv_company_assignment %d, в рабочей %d'
       % (n_a, len(set(ubr) & set(vlad))))
    # ступень и балл по формуле (та же функция, что fixF2_ball)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    E2 = None
    for imya in ('3s_fixF2_ball', 'fixF2_ball'):
        try:
            E2 = __import__(imya)
            break
        except ImportError:
            continue
    novye = list(plan['prodavcy'])
    for inn in novye:
        c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
        if E2:
            d = E2.razbor_kompanii(c, cat.contacts(inn), cat, sales)
            ok(abs(float(score[inn]) - d['score']) < 0.05 and int(stup[inn] or -1) == d['tier'],
               '%s: балл очереди %.1f, ступень %s = формула (%.1f, %d)' % (inn, float(score[inn]), stup[inn], d['score'], d['tier']))
    # рендер
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY, 1):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    rx_dd = re.compile(r'<dt>([^<]+)</dt><dd>(.*?)</dd>', re.S)

    def total(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1

    def filtry(t):
        res = []
        for m in re.finditer(r'<select name="([a-z_]+)"[^>]*>(.*?)</select>', t, re.S):
            for o in re.finditer(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(2)):
                v, lab = H.unescape(o.group(1)), H.unescape(o.group(2)).strip()
                mm = re.search(r'[·–]\s*(\d+)\s*$', lab)
                if v and mm:
                    res.append((m.group(1), v, int(mm.group(1)), lab))
        for m in re.finditer(r'<input type="checkbox" name="([a-z_]+)" value="1"[^>]*>([^<]*)</label>', t):
            lab = H.unescape(m.group(2)).strip()
            mm = re.search(r'·\s*(\d+)\s*$', lab)
            if mm:
                res.append((m.group(1), '1', int(mm.group(1)), lab))
        return list(dict.fromkeys(res))
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats')):
            o = get(u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        ok(total(get('/centro').text) == 600, 'админ, «Вся очередь»: %d' % total(get('/centro').text))
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200 and total(o.text) == 150, '%s: главная %s, в очереди %d' % (p, o.status_code, total(o.text)))
        # карточки 13 новых: админ и свой продавец
        for inn in novye:
            p = vlad.get(inn)
            c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            for kak in ('meyer_admin', p):
                o = get('/centro', kak, params={'inn': inn})
                t = o.text
                dd = {a.strip(): re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', b))).strip() for a, b in rx_dd.findall(t)}
                pusto = [x for x in ('Адрес', 'Директор', 'Статус ЕГРЮЛ', 'Выручка', 'Чистая прибыль') if dd.get(x, '–') in ('', '–')]
                ball = re.search(r'<b>Балл очереди</b>\s*([\d.]+)', t)
                ok(o.status_code == 200 and not pusto and 'База 3' in t and ball and abs(float(ball.group(1)) - float(score[inn])) < 0.05,
                   'карточка %s (%s) у %s: %s; пустые: %s; балл в карточке %s = %s; %s' % (
                       inn, c['predpriyatie'][:28], kak, o.status_code, pusto, ball.group(1) if ball else '?', round(float(score[inn]), 1),
                       (dd.get('Статус ЕГРЮЛ') or '')[:30]))
            drugoy = next(x for x in PRODAVCY if x != p)
            o = get('/centro', drugoy, params={'inn': inn})
            ok(o.status_code != 200 or c['predpriyatie'] not in o.text, 'чужой продавец %s не видит карточку %s: %s' % (drugoy, inn, o.status_code))
        # числа фильтров = строки списка (админ и каждый продавец)
        for kak in ['meyer_admin'] + PRODAVCY:
            t = get('/centro', kak).text
            plohie = []
            fl = filtry(t)
            for imya, v, n, lab in fl:
                if imya in ('sort', 'call_status', 'assigned_user'):
                    continue
                nn = total(get('/centro', kak, params={imya: v}).text)
                if nn != n:
                    plohie.append((imya, v, n, nn))
            ok(not plohie, '%s: пунктов фильтров с числом %d, каждый находит показанное число%s' % (
                kak, len(fl), ('; расхождения: %s' % plohie[:8]) if plohie else ''))
    # холдинги: каждая группа у одного продавца (holding_chlen + пары общих номеров fixD)
    razorv = []
    for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}:
        chl = [r[0] for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)) if r[0] in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((g, chl))
    try:
        hold = json.load(io.open(os.path.join(DROP, 'fixD-holdingi.json'), encoding='utf-8'))
        for pp in hold['obshchie_nomera_bez_svyazi']:
            chl = [i for i in pp['inns'] if i in vse]
            if len({vlad.get(i) for i in chl}) > 1:
                razorv.append(('общий номер', chl))
    except (OSError, ValueError):
        pass
    ok(not razorv, 'каждая группа холдинга и пара с общими номерами – у одного продавца%s' % (
        (': разорваны %s' % razorv[:5]) if razorv else ''))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


# ====================================================================== ТОЧКИ ВХОДА
if '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    raise SystemExit(1 if proverka(sys.argv[i + 1], sys.argv[i + 2]) else 0)

if LOKALNO:
    i = sys.argv.index('--lokalno')
    KAT_, SALES_, APP_, PLAN_ = sys.argv[i + 1:i + 5]
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = KAT_
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = SALES_
    sys.path.insert(0, APP_)
    rabota(KAT_, SALES_, json.load(io.open(PLAN_, encoding='utf-8')), {}, '(локально)', '-lokalno')
    raise SystemExit(0)


def zapustit_proverku(papka):
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True, timeout=1300, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
    io.open(os.path.join(DROP, 'fixG-proverka-%s.txt' % time.strftime('%Y%m%d-%H%M%S')), 'w', encoding='utf-8').write(vyvod)
    for t in (ts, tk):
        try:
            os.remove(t)
        except OSError:
            pass
    return vyvod


if '--vnutri' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    import logging
    logging.disable(logging.CRITICAL)
    if '--tolko-proverka' in sys.argv:
        papka = os.path.join(KOREN, '_bekap', 'fixG-proverka-' + VREMYA)
        os.makedirs(papka, exist_ok=True)
        print(zapustit_proverku(papka)[-5500:])
        raise SystemExit(0)
    plan = json.load(io.open(PLAN, encoding='utf-8'))
    bitrix = json.load(io.open(BITRIX, encoding='utf-8'))
    BEKAP = os.path.join(KOREN, '_bekap', 'fixG-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    if '--suhoy' in sys.argv:
        # репетиция: всё то же на копиях боевых баз, боевые не трогаются
        tk, ts = os.path.join(BEKAP, 'suhoy_kat.db'), os.path.join(BEKAP, 'suhoy_sales.db')
        kopiya(KAT, tk)
        kopiya(SALES, ts)
        for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
            os.environ[kk] = tk
        for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
            os.environ[kk] = ts
        rabota(tk, ts, plan, bitrix, BEKAP, '-suhoy')
        r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True, timeout=1300,
                           cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        print('===== ПРОВЕРКА РЕПЕТИЦИИ (на копиях) =====')
        print((r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-2000:])[-3800:])
        raise SystemExit(0)
    assert os.path.normcase(os.environ.get('CENTRIFUGAL_DB', '')) == os.path.normcase(KAT)
    assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)
    kopiya(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
    kopiya(SALES, os.path.join(BEKAP, 'centro_sales_meyer1.db'))
    print('копии баз (НЕ для отката целиком): %s' % BEKAP)
    rabota(KAT, SALES, plan, bitrix, BEKAP)
    print('===== ПРОВЕРКА (на копиях баз после записи) =====')
    print(zapustit_proverku(BEKAP)[-3500:])
