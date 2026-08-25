# -*- coding: utf-8 -*-
r"""ДОБОР КОНТАКТОВ ИЗ КЭША (разрешён владельцем 25.08).

Выемка НЕ переписана: берём функции из enrich_contacts ровно как в замере
(_harvest_from_html, EMAIL_RE, phones_in, _is_junk_email, rol_iz_imeni_yashchika).
Запись — только через EnrichDB.add_email / add_phone: там стоят рубежи против
реквизитов и против понижения точной роли.

Метки:
  source='кэш-добор' у почт и телефонов;
  pometka='кэш-добор' у почт — потому что add_email САМ переписывает source в
  'own-site', когда хост страницы совпадает с сайтом компании, и метка бы
  потерялась; pometka он сохраняет как есть, по ней и откатывать;
  номер, уже стоящий за ДРУГИМ ИНН, пишется как общий: role='общий' и
  'общий номер: N предприятий' в source — та же запись, что делает сам add_phone.

best_email не трогаем вовсе (add_email его не пишет).

Запускается сам себя детачедом: прогон на два часа, а раннер режет задание.
Журнал с fsync после каждой пачки, резюм по журналу.
"""
import gzip
import json
import os
import re
import subprocess
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.environ['NO_BROWSER'] = '1'

KESH = r'C:\seostat\drop\pagecache'
ZHURNAL = r'C:\sender\_tmp\kesh-dobor.jsonl'
ITOG = r'C:\sender\_tmp\kesh-dobor-itog.json'
LOG = r'C:\sender\_tmp\kesh-dobor.out'
PACHKA = 40
PAUZA = 3.0
# доли из замера на 260 компаниях — с ними сверяемся на ходу
BAZA_POCHTA = 0.550
BAZA_TELEFON = 0.565
PROVERKA_POSLE = 200

# ---------- запуск детачедом ----------
if os.environ.get('DOBOR_CHILD') != '1':
    env = dict(os.environ)
    env['DOBOR_CHILD'] = '1'
    f = open(LOG, 'a', encoding='utf-8')
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                         cwd=DIR, env=env, stdout=f, stderr=subprocess.STDOUT,
                         creationflags=0x00000008 | 0x00000200)  # DETACHED|NEW_GROUP
    print('добор запущен детачедом, pid=%s, лог %s' % (p.pid, LOG))
    sys.exit(0)

import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB  # noqa: E402


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def norm10(s):
    d = re.sub(r'\D', '', s or '')
    if len(d) == 11 and d[0] in '78':
        d = d[1:]
    return d if len(d) == 10 else ''


def vyemka(inn):
    """Ровно то, что делает crawl_contacts по каждой странице — но с диска."""
    p = os.path.join(KESH, inn + '.json.gz')
    try:
        with gzip.open(p, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        return None, None, str(e)[:80]
    pochta_url, tel_url = {}, {}
    for pg in (j.get('pages') or []):
        h = pg.get('html') or ''
        u = pg.get('url') or ''
        if not h:
            continue
        pe, ph = EC._harvest_from_html(h)
        pt = re.sub(r'<[^>]+>', ' ',
                    re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I))
        for e in EC.EMAIL_RE.findall(pt):
            pe.add(e.lower())
        for m in EC.phones_in(pt):
            ph.add(re.sub(r'\D', '', m.group(0)))
        for e in pe:
            if e.endswith(EC._IMG_EXT):
                continue
            pochta_url.setdefault(e, u)
        for t in ph:
            d = norm10(t)
            if d:
                tel_url.setdefault(d, u)
    return pochta_url, tel_url, ''


def main():
    t_start = time.time()
    # --- цели: кэш есть, контактов нет; пересчитываем сами ---
    db0 = EDB.EnrichDB()
    db0.cx.execute('PRAGMA busy_timeout=60000')
    s_email = {str(r[0]) for r in db0.cx.execute('select distinct inn from emails')}
    s_phone = {str(r[0]) for r in db0.cx.execute('select distinct inn from phone_contacts')}
    komp = {str(r[0]) for r in db0.cx.execute('select inn from companies')}
    # карта «десять цифр -> чей ИНН» для отметки общих номеров
    chey = {}
    for inn, ph in db0.cx.execute('select inn, phone from phone_contacts'):
        d = norm10(ph)
        if d:
            chey.setdefault(d, str(inn))
    db0.cx.close()
    log('в базе телефонов уникальных по 10 цифрам:', len(chey))

    kesh = [n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')]
    celi = sorted(i for i in kesh if i not in s_email and i not in s_phone and i in komp)
    sdelano = set()
    if os.path.exists(ZHURNAL):
        with open(ZHURNAL, encoding='utf-8') as f:
            for s in f:
                try:
                    sdelano.add(json.loads(s)['inn'])
                except Exception:  # noqa: BLE001
                    continue
    ochered = [i for i in celi if i not in sdelano]
    log('целей %d, уже сделано %d, к работе %d' % (len(celi), len(sdelano), len(ochered)))

    itog = {'компаний_обработано': 0, 'компаний_с_почтой': 0, 'компаний_с_телефоном': 0,
            'почт_записано': 0, 'телефонов_записано': 0, 'телефонов_общих': 0,
            'почт_отсеяно_мусор': 0, 'телефонов_отсеяно_рубежом': 0,
            'пропущено_появились_контакты': 0, 'кэш_не_прочитался': 0,
            'компаний_пусто': 0, 'остановка': ''}
    primery = []

    for start in range(0, len(ochered), PACHKA):
        pachka = ochered[start:start + PACHKA]
        dobycha = []
        for inn in pachka:
            po, te, err = vyemka(inn)
            if po is None:
                itog['кэш_не_прочитался'] += 1
                dobycha.append((inn, {}, {}, err))
                continue
            chistye = {e: u for e, u in po.items() if not EC._is_junk_email(e)}
            itog['почт_отсеяно_мусор'] += len(po) - len(chistye)
            dobycha.append((inn, chistye, te, ''))

        db = EDB.EnrichDB()
        db.cx.execute('PRAGMA busy_timeout=60000')
        stroki = []
        for inn, po, te, err in dobycha:
            # ещё раз: не появились ли контакты у соседнего процесса
            if db.cx.execute('select 1 from emails where inn=? limit 1', (inn,)).fetchone() \
                    or db.cx.execute('select 1 from phone_contacts where inn=? limit 1',
                                     (inn,)).fetchone():
                itog['пропущено_появились_контакты'] += 1
                stroki.append({'inn': inn, 'пропуск': 'контакты появились', 'p': 0, 't': 0})
                continue
            itog['компаний_обработано'] += 1
            np = nt = nobsh = 0
            for e, u in sorted(po.items()):
                db.add_email(inn, e, role=EC.rol_iz_imeni_yashchika(e),
                             source='кэш-добор', source_url=u, pometka='кэш-добор')
                np += 1
            for d, u in sorted(te.items()):
                vladelec = chey.get(d)
                obshchiy = bool(vladelec and vladelec != inn)
                src = 'кэш-добор'
                rol = ''
                if obshchiy:
                    rol = 'общий'
                    src = 'кэш-добор; общий номер: стоит за ИНН ' + vladelec
                if db.add_phone(inn, '+7' + d, role=rol, source=src, source_url=u):
                    nt += 1
                    nobsh += 1 if obshchiy else 0
                    chey.setdefault(d, inn)
                else:
                    itog['телефонов_отсеяно_рубежом'] += 1
            itog['почт_записано'] += np
            itog['телефонов_записано'] += nt
            itog['телефонов_общих'] += nobsh
            itog['компаний_с_почтой'] += 1 if np else 0
            itog['компаний_с_телефоном'] += 1 if nt else 0
            itog['компаний_пусто'] += 1 if not (np or nt) else 0
            if np or nt:
                if len(primery) < 40:
                    primery.append({'inn': inn, 'почт': np, 'телефонов': nt,
                                    'общих': nobsh,
                                    'примеры_почт': sorted(po)[:3],
                                    'примеры_тел': ['+7' + d for d in sorted(te)[:3]]})
            stroki.append({'inn': inn, 'p': np, 't': nt, 'obsh': nobsh,
                           'pochty': sorted(po), 'tel': ['+7' + d for d in sorted(te)],
                           'ts': time.strftime('%Y-%m-%dT%H:%M:%S')})
        db.cx.close()

        with open(ZHURNAL, 'a', encoding='utf-8') as f:
            for s in stroki:
                f.write(json.dumps(s, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

        n = itog['компаний_обработано']
        log('пачка %d-%d | обработано %d | почт %d | тел %d (общих %d)'
            % (start, start + len(pachka), n, itog['почт_записано'],
               itog['телефонов_записано'], itog['телефонов_общих']))

        # --- страховка: сверка с замером ---
        if n >= PROVERKA_POSLE and not itog['остановка']:
            dp = itog['компаний_с_почтой'] / n
            dt = itog['компаний_с_телефоном'] / n
            if dp < BAZA_POCHTA / 2 or dp > min(1.0, BAZA_POCHTA * 2) or \
               dt < BAZA_TELEFON / 2 or dt > min(1.0, BAZA_TELEFON * 2):
                itog['остановка'] = ('доли разошлись с замером: почта %.3f (было %.3f), '
                                     'телефон %.3f (было %.3f)'
                                     % (dp, BAZA_POCHTA, dt, BAZA_TELEFON))
                log('СТОП:', itog['остановка'])
                break
        time.sleep(PAUZA)

    itog['секунд'] = round(time.time() - t_start)
    itog['примеры'] = primery
    itog['копия_базы'] = r'C:\sender\_tmp\enrich-pered-kesh-doborom-20260825-1831.db'
    if itog['компаний_обработано']:
        itog['доля_с_почтой'] = round(itog['компаний_с_почтой'] / itog['компаний_обработано'], 3)
        itog['доля_с_телефоном'] = round(itog['компаний_с_телефоном'] / itog['компаний_обработано'], 3)
    with open(ITOG, 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    log('ГОТОВО', json.dumps(itog, ensure_ascii=False)[:600])


if __name__ == '__main__':
    main()
