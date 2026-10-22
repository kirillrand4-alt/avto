# -*- coding: utf-8 -*-
r"""fixKN (22.10): панель КЦ – у компаний «КО» старые контакты заменяются контактами из файлов владельца (со ссылкой на
источник) и ставятся метки Битрикса. Пакет – KN-paket.json на дропе (готовит fixKN_podgotovka.py из xlsx владельца).

Владелец 22.10: «убери эти данные из панели, замени этими с ссылкой на источник»; «проставь метки: в Битриксе активная
сделка КЦ = плохо (красный)… „Общая воронка“ – белым… только СЦ – зелёный… провалены / прошли – тоже зелёный… если сделок
нет – не ставь метку; в метке просто пиши, какие идут». План согласован («делай»): у 106 компаний «КО» без новых данных
старые контакты остаются; у 417 компаний с новыми – уходят и «Люди», и телефоны / почты реквизитов.

Что меняет (каталог C:\seostat\data\centrifugal.db + два шаблона, больше ничего):
  * у 417 компаний (inn_zamena пакета): строки contact и person переносятся в contact_arhiv_fixKN / person_arhiv_fixKN
    (не удаляются насовсем), поля реквизитов telefony_checko, pochty_checko, pochta, telefony_iz_bazy, telefony_predpriyatiya
    и счётчики n_phones / has_phone / n_tech / has_tech / n_purchaser / has_purchaser – в company_pole_arhiv_fixKN; вставляются
    новые контакты (порядок – по лесенке прозвона), счётчики пересчитываются по ним; отметка – таблица import_fixKN;
  * у 523 компаний «КО»: колонки company.bitrix_metka (krasnaya / belaya / zelenaya / пусто), bitrix_tekst, bitrix_podrobno;
  * app\templates\_ochered_spisok.html – метка под названием компании в строке списка;
  * app\templates\centro.html – метка вверху карточки (у p25 колонки нет – 8014 рендерит байт в байт как раньше).
Код Python не меняется; шаблоны панель перечитывает сама (проверяется живым запросом, иначе nssm restart obzvon).
Порядок очереди, статусы, комментарии, назначения – не трогаются (база продаж вообще не открывается на запись).

Проверка (копии каталога и баз в C:\seostat\_stage\fixKN-<время>): данные – у 417 ровно контакты пакета, у прочих компаний
строки contact / person / company не изменились (хеш), метки по цветам = пакету; рендер (TestClient) «до» и «после»: в
карточках 417 – только новые контакты со всеми ссылками, без «Людей» и «Телефонов (чеко)», с меткой; карточки остальных и
p25 – байт в байт как до; список – метки у своих строк.

    python3 zapusk_na_servere.py fixKN_primenit.py --suho
    python3 zapusk_na_servere.py fixKN_primenit.py --primenit
    python3 zapusk_na_servere.py fixKN_primenit.py --otkat C:\seostat\_bekap\fixKN-<время>
Откат (--otkat): каталог – из копии (sqlite backup), шаблоны – из копии. Каталог пишет только офлайн-сборка, поэтому возврат
копии ничего чужого не теряет. Если каталог пересоберут (build_centro_db.py), старые контакты вернутся – тогда этот скрипт
просто запустить снова.
"""
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\seostat'
DATA = os.path.join(KOREN, 'data')
KAT = os.path.join(DATA, 'centrifugal.db')
DROP = r'C:\seostat\drop\drop-storage'
PAKET = os.path.join(DROP, 'KN-paket.json')
ZAMOK = os.path.join(KOREN, '_zamok.txt')
T = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_stage', 'fixKN-' + T)
BEKAP = os.path.join(KOREN, '_bekap', 'fixKN-' + T)
SPISOK_REL = os.path.join('app', 'templates', '_ochered_spisok.html')
CEN_REL = os.path.join('app', 'templates', 'centro.html')
PRAVIM = (SPISOK_REL, CEN_REL)
POLYA_REKV = ('telefony_checko', 'pochty_checko', 'pochta', 'telefony_iz_bazy', 'telefony_predpriyatiya')
SCHETCHIKI = ('n_phones', 'has_phone', 'n_tech', 'has_tech', 'n_purchaser', 'has_purchaser')
KOL_KONTAKTA = ('inn', 'value', 'kind', 'person', 'role', 'position', 'phone_type', 'source', 'source_url', 'is_purchaser',
                'is_tech', 'has_role', 'is_unknown_owner', 'nomer_ne_lichnyy')
log = []

# ======================================================================== шаблоны
CVETA = ("{'krasnaya': 'background:#fdecec;border:1px solid #f3c2c2;color:#9b1c1c', "
         "'zelenaya': 'background:#e8f6ee;border:1px solid #b7e1c7;color:#17663a', "
         "'belaya': 'background:#ffffff;border:1px solid #c9ced8;color:#344054'}")
SPISOK_PRAVKI = [
    ('метка в строке списка',
     '<td><a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>',
     '<td><a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>'
     '{# fixKN 22.10: метка Битрикса – красная: идёт сделка КЦ, белая: только «Общая воронка», зелёная: прочие сделки #}'
     '{% if c.bitrix_metka %}<br><span class="bx-metka" style="{{ ' + CVETA + '.get(c.bitrix_metka, \'\') }}" '
     'title="{{ c.bitrix_podrobno or \'\' }}">{{ c.bitrix_tekst }}</span>{% endif %}', 1),
    ('стиль метки', '.och-mashiny{max-width:260px}',
     '.och-mashiny{max-width:260px}\n.bx-metka{display:inline-block;margin-top:4px;padding:2px 8px;border-radius:6px;font-size:12px;'
     'font-weight:600;line-height:1.35;max-width:340px;white-space:normal}', 1),
]
CEN_PRAVKI = [
    ('метка в карточке', '      <div class="hero-badges">\n        <span class="tag tag-status">',
     '      <div class="hero-badges">\n        {% if company.bitrix_metka %}<span class="tag" style="{{ ' + CVETA + '.get(company.bitrix_metka, \'\') }};'
     'white-space:normal;max-width:640px;font-weight:600" title="{{ company.bitrix_podrobno or \'\' }}">{{ company.bitrix_tekst }}</span>'
     '{% endif %}<span class="tag tag-status">', 1),
]
PRIZNAK = 'bitrix_metka'


def p(*a):
    s = ' '.join(str(x) for x in a)
    log.append(s)
    print(s, flush=True)


def sha(t):
    return hashlib.sha256(t if isinstance(t, bytes) else t.encode('utf-8')).hexdigest()[:16]


def esc(s):
    """Как экранирует Jinja (markupsafe): & < > " '."""
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&#34;').replace("'", '&#39;'))


def chitat(put):
    return io.open(put, encoding='utf-8', newline='').read() if os.path.exists(put) else None


def pisat(put, t):
    with io.open(put, 'w', encoding='utf-8', newline='') as f:
        f.write(t)


def pravki_shablonov(koren) -> list:
    sd = []
    for rel, spisok in ((SPISOK_REL, SPISOK_PRAVKI), (CEN_REL, CEN_PRAVKI)):
        put = os.path.join(koren, rel)
        t = chitat(put)
        if PRIZNAK in t:
            sd.append('%s: уже есть' % os.path.basename(rel))
            continue
        nl = '\r\n' if '\r\n' in t else '\n'
        for imya, staroe, novoe, n_ozh in spisok:
            staroe, novoe = staroe.replace('\n', nl), novoe.replace('\n', nl)
            if t.count(staroe) != n_ozh:
                raise SystemExit('%s: «%s» – якорь найден %d раз' % (rel, imya, t.count(staroe)))
            t = t.replace(staroe, novoe)
        pisat(put, t)
        sd.append('%s: %d правок' % (os.path.basename(rel), len(spisok)))
    return sd


# ======================================================================== каталог
def kopiya_bazy(src, dst, ro=True):
    a = sqlite3.connect(('file:%s?mode=ro' % src) if ro else src, uri=ro, timeout=60)
    b = sqlite3.connect(dst, timeout=60)
    a.backup(b)
    b.close()
    a.close()


def otpechatok(put_db, inn_isklyuchit) -> dict:
    """Хеш строк contact / person / company всех компаний, КРОМЕ указанных, – прочие не должны измениться ни на байт."""
    k = sqlite3.connect('file:%s?mode=ro' % put_db, uri=True)
    out = {}
    for t in ('contact', 'person', 'company'):
        kol = [r[1] for r in k.execute('PRAGMA table_info(%s)' % t) if not r[1].startswith('bitrix_')]
        h = hashlib.sha256()
        for r in k.execute('SELECT %s FROM %s ORDER BY %s' % (', '.join('"%s"' % c for c in kol), t, 'id' if 'id' in kol else 'inn')):
            if str(r[kol.index('inn')]) not in inn_isklyuchit:
                h.update(repr(r).encode('utf-8'))
        out[t] = h.hexdigest()[:16]
    k.close()
    return out


def primenit_k_katalogu(put_db, paket) -> dict:
    """Одна транзакция. Идемпотентно: ИНН, уже заменённый этим пакетом (import_fixKN, число контактов совпадает), пропускается."""
    zam = paket['inn_zamena']
    po_inn = {}
    for kk in paket['kontakty']:
        po_inn.setdefault(kk['inn'], []).append(kk)
    s = sqlite3.connect(put_db, timeout=60)
    st = {'zameneno': 0, 'uzhe': 0, 'kontaktov_v_arhiv': 0, 'lyudey_v_arhiv': 0, 'poley_v_arhiv': 0, 'kontaktov_novyh': 0}
    try:
        s.execute('BEGIN IMMEDIATE')
        kol_c = [r[1] for r in s.execute('PRAGMA table_info(contact)')]
        kol_p = [r[1] for r in s.execute('PRAGMA table_info(person)')]
        kol_co = [r[1] for r in s.execute('PRAGMA table_info(company)')]
        if [r[2] for r in s.execute('PRAGMA table_info(contact)') if r[1] == 'inn'] != ['TEXT']:
            st['tip_inn_contact'] = [r[2] for r in s.execute('PRAGMA table_info(contact)') if r[1] == 'inn']
        s.execute('CREATE TABLE IF NOT EXISTS contact_arhiv_fixKN AS SELECT *, \'\' AS arhiv_kogda FROM contact WHERE 0')
        s.execute('CREATE TABLE IF NOT EXISTS person_arhiv_fixKN AS SELECT *, \'\' AS arhiv_kogda FROM person WHERE 0')
        s.execute('CREATE TABLE IF NOT EXISTS company_pole_arhiv_fixKN (inn TEXT, pole TEXT, znachenie TEXT, arhiv_kogda TEXT)')
        s.execute('CREATE TABLE IF NOT EXISTS import_fixKN (inn TEXT PRIMARY KEY, kontaktov INTEGER, kogda TEXT, paket TEXT)')
        for kol in ('bitrix_metka', 'bitrix_tekst', 'bitrix_podrobno'):
            if kol not in kol_co:
                s.execute('ALTER TABLE company ADD COLUMN %s TEXT' % kol)
        kogda = time.strftime('%Y-%m-%dT%H:%M:%S')
        rekv = [c for c in POLYA_REKV + SCHETCHIKI if c in kol_co]
        for inn in zam:
            novye = po_inn.get(inn, [])
            bylo = s.execute('SELECT kontaktov FROM import_fixKN WHERE inn=?', (inn,)).fetchone()
            seychas = s.execute('SELECT COUNT(*) FROM contact WHERE inn=?', (inn,)).fetchone()[0]
            if bylo and bylo[0] == seychas == len(novye):
                st['uzhe'] += 1
                continue
            if not s.execute('SELECT 1 FROM company WHERE inn=?', (inn,)).fetchone():
                raise SystemExit('ИНН %s нет в каталоге company – стоп' % inn)
            st['kontaktov_v_arhiv'] += s.execute('INSERT INTO contact_arhiv_fixKN SELECT *, ? FROM contact WHERE inn=?', (kogda, inn)).rowcount
            s.execute('DELETE FROM contact WHERE inn=?', (inn,))
            st['lyudey_v_arhiv'] += s.execute('INSERT INTO person_arhiv_fixKN SELECT *, ? FROM person WHERE inn=?', (kogda, inn)).rowcount
            s.execute('DELETE FROM person WHERE inn=?', (inn,))
            stroka = s.execute('SELECT %s FROM company WHERE inn=?' % ', '.join('"%s"' % c for c in rekv), (inn,)).fetchone()
            for c, v in zip(rekv, stroka):
                if v not in (None, '', 0):
                    s.execute('INSERT INTO company_pole_arhiv_fixKN VALUES (?,?,?,?)', (inn, c, str(v), kogda))
                    st['poley_v_arhiv'] += 1
            nov = {'n_phones': sum(1 for x in novye if x['kind'] == 'phone'), 'n_tech': sum(x['is_tech'] for x in novye),
                   'n_purchaser': sum(x['is_purchaser'] for x in novye)}
            nov.update(has_phone=int(nov['n_phones'] > 0), has_tech=int(nov['n_tech'] > 0), has_purchaser=int(nov['n_purchaser'] > 0))
            nov.update({c: None for c in POLYA_REKV})
            nov = {c: v for c, v in nov.items() if c in kol_co}
            s.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % c for c in nov), list(nov.values()) + [inn])
            for x in novye:
                s.execute('INSERT INTO contact (%s) VALUES (%s)' % (', '.join(KOL_KONTAKTA), ','.join('?' * len(KOL_KONTAKTA))),
                          [x[c] for c in KOL_KONTAKTA])
            st['kontaktov_novyh'] += len(novye)
            s.execute('INSERT OR REPLACE INTO import_fixKN VALUES (?,?,?,?)', (inn, len(novye), kogda, ' + '.join(paket['istochnik'])))
            st['zameneno'] += 1
        metki = paket['metki']
        for inn in paket['inn_ko']:
            m = metki.get(inn) or {}
            s.execute('UPDATE company SET bitrix_metka=?, bitrix_tekst=?, bitrix_podrobno=? WHERE inn=?',
                      (m.get('metka'), m.get('tekst'), m.get('podrobno'), inn))
        st['metki'] = dict(s.execute('SELECT COALESCE(bitrix_metka, \'—\'), COUNT(*) FROM company WHERE bitrix_metka IS NOT NULL GROUP BY 1').fetchall())
        s.execute('COMMIT')
    except BaseException:
        if s.in_transaction:
            s.execute('ROLLBACK')
        raise
    finally:
        s.close()
    return st


def proverit_katalog(do_db, posle_db, paket, plokh):
    zam = set(paket['inn_zamena'])
    po_inn = {}
    for kk in paket['kontakty']:
        po_inn.setdefault(kk['inn'], []).append(kk)
    a, b = otpechatok(do_db, zam), otpechatok(posle_db, zam)
    for t in a:
        if a[t] != b[t]:
            plokh.append('каталог: у прочих компаний изменилась таблица %s' % t)
    k = sqlite3.connect('file:%s?mode=ro' % posle_db, uri=True)
    d = sqlite3.connect('file:%s?mode=ro' % do_db, uri=True)
    n_kont = dict(k.execute('SELECT inn, COUNT(*) FROM contact GROUP BY inn').fetchall())
    n_ludi = dict(k.execute('SELECT inn, COUNT(*) FROM person GROUP BY inn').fetchall())
    ne_tak = [i for i in zam if n_kont.get(i, 0) != len(po_inn.get(i, [])) or n_ludi.get(i, 0)]
    if ne_tak:
        plokh.append('каталог: у %d из %d компаний число контактов не равно пакету или остались люди: %s' % (len(ne_tak), len(zam), ne_tak[:5]))
    bylo_c = d.execute('SELECT COUNT(*) FROM contact WHERE inn IN (%s)' % ','.join('?' * len(zam)), sorted(zam)).fetchone()[0]
    v_arh = k.execute('SELECT COUNT(*) FROM contact_arhiv_fixKN').fetchone()[0]
    if bylo_c != v_arh:
        plokh.append('каталог: было контактов у 417 – %d, в архиве %d' % (bylo_c, v_arh))
    bez_ssylki = k.execute("SELECT COUNT(*) FROM contact WHERE inn IN (%s) AND COALESCE(source_url,'') NOT LIKE 'http%%'"
                           % ','.join('?' * len(zam)), sorted(zam)).fetchone()[0]
    if bez_ssylki:
        plokh.append('каталог: у %d новых контактов нет ссылки' % bez_ssylki)
    ozh = {}
    for m in paket['metki'].values():
        ozh[m['metka']] = ozh.get(m['metka'], 0) + 1
    est = dict(k.execute('SELECT bitrix_metka, COUNT(*) FROM company WHERE bitrix_metka IS NOT NULL GROUP BY 1').fetchall())
    if est != ozh:
        plokh.append('каталог: метки %s, в пакете %s' % (est, ozh))
    p('каталог: было у 417 контактов %d (в архиве %d), людей в архиве %d; стало контактов %d; метки %s; типы inn: %s' % (
        bylo_c, v_arh, k.execute('SELECT COUNT(*) FROM person_arhiv_fixKN').fetchone()[0],
        sum(n_kont.get(i, 0) for i in zam), est, k.execute('SELECT typeof(inn), COUNT(*) FROM contact GROUP BY 1').fetchall()))
    k.close()
    d.close()


# ---------------------------------------------------------------- проверка рендера в отдельном процессе (venv)
NORM = [(re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:\d{2}|Z)?'), '<ВРЕМЯ>'),
        (re.compile(r'\d{2}\.\d{2}(\.\d{4})?,? \d{2}:\d{2}'), '<ВРЕМЯ>')]


def norm(t):
    for r, z in NORM:
        t = r.sub(z, t)
    return t


def proverka(var_koren, konf, obrazcy_json, vyhod):
    sys.path.insert(0, var_koren)
    os.chdir(var_koren)
    import logging
    logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from app.obzvon import create_app
    from app.api import routes_centro_sales as rcs
    vn = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vn.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'admin', 'role': 'admin', 'is_active': 1}
    k = TestClient(vn, follow_redirects=False)
    bp = {'kc': '/obzvon', 'p25': '/p25'}[konf]
    obrazcy = json.loads(obrazcy_json)
    res = {}
    for url in ['/centro', '/centro?size=100', '/centro?page=2&size=100', '/centro?call_status=dubl'] + ['/centro?inn=' + i for i in obrazcy]:
        r = k.get(bp + url)
        if r.status_code == 404 and '?inn=' in url:      # компания не в «Вся очередь» – открыть в её вкладке
            for st in ('dubl', 'ne_ponravilas', 'v_rabote'):
                r = k.get(bp + url + '&call_status=' + st)
                if r.status_code != 404:
                    break
        t = r.text
        res[url] = {'kod': r.status_code, 'sha': sha(norm(t)), 'kontaktov': t.count('<article class="contact-card'),
                    'lyudi': t.count('<article class="person-card'), 'cheko': 'Телефоны (чеко)' in t,
                    'metok': t.count('class="bx-metka"') + t.count('title="Битрикс'), 'telo': t}
    io.open(vyhod, 'w', encoding='utf-8').write(json.dumps(res, ensure_ascii=False))


def stadiya(paket) -> bool:
    os.makedirs(os.path.join(STAGE, 'db'), exist_ok=True)
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    do_k, posle_k = os.path.join(STAGE, 'do'), os.path.join(STAGE, 'posle')
    shutil.copytree(os.path.join(KOREN, 'app'), os.path.join(do_k, 'app'), ignore=ign)
    shutil.copytree(os.path.join(do_k, 'app'), os.path.join(posle_k, 'app'))
    p('шаблоны в stage:', pravki_shablonov(posle_k))
    kat_do, kat_posle = os.path.join(STAGE, 'db', 'kat-do.db'), os.path.join(STAGE, 'db', 'kat-posle.db')
    kopiya_bazy(KAT, kat_do)
    shutil.copy(kat_do, kat_posle)
    p('каталог в stage:', primenit_k_katalogu(kat_posle, paket))
    p('повторный прогон (идемпотентность):', primenit_k_katalogu(kat_posle, paket))
    plokh = []
    proverit_katalog(kat_do, kat_posle, paket, plokh)
    # образцы карточек: по одной красной, белой, зелёной, без метки (с заменой), «КО» без новых, не «КО»
    zam, metki, ko = set(paket['inn_zamena']), paket['metki'], set(paket['inn_ko'])
    obr = []
    for cvet in ('krasnaya', 'belaya', 'zelenaya'):
        obr.append(next(i for i in paket['inn_zamena'] if metki.get(i, {}).get('metka') == cvet))
    obr.append(next(i for i in paket['inn_zamena'] if i not in metki))
    obr.append(next(i for i in paket['inn_ko'] if i not in zam))
    k = sqlite3.connect('file:%s?mode=ro' % os.path.join(DATA, 'centro_sales.db'), uri=True)
    vrab = [r[0] for r in k.execute("SELECT inn FROM company_state WHERE call_result='v_rabote' LIMIT 50")]
    k.close()
    obr.append(next((i for i in vrab if i not in ko), ''))
    obr = [i for i in obr if i]
    sales = {}
    for konf, sdb in (('kc', 'centro_sales.db'), ('p25', 'p25_sales.db')):
        sales[konf] = os.path.join(STAGE, 'db', '%s-sales.db' % konf)
        kopiya_bazy(os.path.join(DATA, sdb), sales[konf])
    p25_kat = os.path.join(STAGE, 'db', 'p25-kat.db')
    kopiya_bazy(os.path.join(DATA, 'p25.db'), p25_kat)
    procy = []
    for konf, imya, k_, kat in (('kc', 'do', do_k, kat_do), ('kc', 'posle', posle_k, kat_posle),
                                ('p25', 'do', do_k, p25_kat), ('p25', 'posle', posle_k, p25_kat)):
        sd = os.path.join(STAGE, 'db', '%s-sales-%s.db' % (konf, imya))
        shutil.copy(sales[konf], sd)
        env = {x: v for x, v in os.environ.items() if not x.startswith(('CENTRO', 'PARK_', 'OBZVON', 'CENTRIFUGAL'))}
        env.update(PYTHONIOENCODING='utf-8', PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=k_,
                   OBZVON_ROOT_PATH={'kc': '/obzvon', 'p25': '/p25'}[konf], CENTRO_SALES_DB=sd, CENTRIFUGAL_DB=kat, CENTRO_DB=kat,
                   PARK_OCHERED_SALES_DB=sd, PARK_OCHERED_DB=kat, PARK_PANEL_DB=os.path.join(STAGE, 'db', 'net-park.db'),
                   CENTRO_SESSION_SECRET='x' * 40)
        vyh = os.path.join(STAGE, '%s-%s.json' % (konf, imya))
        procy.append((konf, imya, vyh, subprocess.Popen(
            [VENV, os.path.abspath(__file__), '--proverka', k_, konf, json.dumps(obr if konf == 'kc' else []), vyh],
            cwd=k_, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)))
    rez = {}
    for konf, imya, vyh, pr in procy:
        out = pr.communicate(timeout=1300)[0].decode('utf-8', 'replace')
        if pr.returncode or not os.path.exists(vyh):
            p('ПРОВЕРКА %s/%s УПАЛА rc=%s:\n%s' % (konf, imya, pr.returncode, out[-2500:]))
            return False
        rez[(konf, imya)] = json.load(io.open(vyh, encoding='utf-8'))
    def ochistit(t):
        # ожидаемые отличия: строка стиля метки в списке и блок «Какая база подключена» (размер и время каталога)
        t = re.sub(r'<details class="database-info">.*?</details>', '', t, flags=re.S)
        return norm(t.replace(SPISOK_PRAVKI[1][2][len(SPISOK_PRAVKI[1][1]):], ''))

    def raznica(a, b, chto):
        import difflib
        if sha(ochistit(a)) == sha(ochistit(b)):
            return False
        p('   разница %s:' % chto)
        for l in list(difflib.unified_diff(ochistit(a).splitlines(), ochistit(b).splitlines(), lineterm='', n=0))[2:14]:
            p('      ' + l[:240])
        return True

    # p25 – как до (кроме строки стиля метки)
    for url, v in rez[('p25', 'do')].items():
        if raznica(v['telo'], rez[('p25', 'posle')][url]['telo'], 'p25 ' + url):
            plokh.append('p25 %s: страница изменилась' % url)
    do, po = rez[('kc', 'do')], rez[('kc', 'posle')]
    po_inn = {}
    for kk in paket['kontakty']:
        po_inn.setdefault(kk['inn'], []).append(kk)
    for inn in obr:
        url = '/centro?inn=' + inn
        a, b = do[url], po[url]
        opis = '%s (%s)' % (inn, 'замена' if inn in zam else ('КО без новых' if inn in ko else 'не КО'))
        if a['kod'] != 200 or b['kod'] != 200:
            plokh.append('карточка %s: коды %s -> %s' % (opis, a['kod'], b['kod']))
            continue
        if inn in zam:
            ssylki = [u for x in po_inn[inn] for u in x['source_url'].split(' ; ')]
            net = [u for u in ssylki if esc(u) not in b['telo']]
            m = metki.get(inn)
            usl = {'контактов = пакету': b['kontaktov'] == len(po_inn[inn]), 'людей нет': b['lyudi'] == 0,
                   'нет «Телефоны (чеко)»': not b['cheko'], 'все ссылки в карточке': not net,
                   'метка': (m is None and 'title="Битрикс' not in b['telo']) or (m is not None and esc(m['tekst']) in b['telo'])}
            p('   карточка %s: было контактов %d, людей %d -> стало %d, людей %d; %s' % (
                opis, a['kontaktov'], a['lyudi'], b['kontaktov'], b['lyudi'], m and m['metka']))
            if not all(usl.values()):
                plokh.append('карточка %s: %s (нет ссылок %d)' % (opis, usl, len(net)))
        else:
            # без замены контактов карточка та же; у «КО» с меткой добавляется только сама метка
            m = metki.get(inn)
            bb = b['telo']
            if m:
                if esc(m['tekst']) not in bb:
                    plokh.append('карточка %s: нет метки «%s»' % (opis, m['tekst']))
                bb = re.sub(r'<span class="tag" style="[^"]*" title="[^"]*">[^<]*</span>(?=<span class="tag tag-status">)', '', bb, count=1)
            if raznica(a['telo'], bb, 'карточка ' + opis):
                plokh.append('карточка %s изменилась не только меткой' % opis)
                continue
            p('   карточка %s: контакты без изменений (%d)%s' % (opis, a['kontaktov'], ', метка ' + m['metka'] if m else ''))
            continue
    # список: метки у своих строк
    n_metok, n_ozh = 0, 0
    for url in ('/centro?size=100', '/centro?page=2&size=100', '/centro?call_status=dubl'):
        t = po[url]['telo']
        inns = re.findall(r'<tr data-href="[^"]*inn=(\d{10,12})', t)
        n_ozh += sum(1 for i in inns if i in metki)
        n_metok += t.count('class="bx-metka"')
        if do[url]['kod'] != 200 or po[url]['kod'] != 200:
            plokh.append('список %s: коды %s -> %s' % (url, do[url]['kod'], po[url]['kod']))
    if n_metok != n_ozh:
        plokh.append('список: меток %d, а строк с меткой %d' % (n_metok, n_ozh))
    p('список: на 2 страницах по 100 и во вкладке «Дубль» меток %d (ждали %d)' % (n_metok, n_ozh))
    for x in plokh:
        p('ПЛОХО: ' + x)
    p('ПЛОХИХ ПРОВЕРОК: %d' % len(plokh))
    if not plokh:
        io.open(os.path.join(DROP, 'fixKN-kartochka-krasnaya.html'), 'w', encoding='utf-8').write(po['/centro?inn=' + obr[0]]['telo'])
        io.open(os.path.join(DROP, 'fixKN-spisok.html'), 'w', encoding='utf-8').write(po['/centro?size=100']['telo'])
    return not plokh


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


urllib.request.install_opener(urllib.request.build_opener(BezRedirekta))
ZHIVYE = [(8012, '/obzvon/centro/login'), (8012, '/obzvon/centro'), (8014, '/p25/centro/login'), (8011, '/')]


def http(port, url):
    try:
        return urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, url), timeout=30).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001
        return str(e)[:60]


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def vernut(papka):
    for rel in PRAVIM:
        shutil.copy2(os.path.join(papka, rel), os.path.join(KOREN, rel))
    kopiya_bazy(os.path.join(papka, 'centrifugal.db'), KAT)


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else '--suho'
    if rezhim == '--proverka':
        return proverka(*sys.argv[2:6])
    if rezhim == '--otkat':
        vzyat_zamok('fixKN откат')
        try:
            vernut(sys.argv[2])
            p('шаблоны и каталог возвращены из', sys.argv[2])
        finally:
            os.remove(ZAMOK)
        return
    p('fixKN %s, %s' % (rezhim, T))
    paket = json.load(io.open(PAKET, encoding='utf-8'))
    p('пакет: компаний с заменой %d, контактов %d, меток %d, КО %d, источники %s' % (
        len(paket['inn_zamena']), len(paket['kontakty']), len(paket['metki']), len(paket['inn_ko']), paket['istochnik']))
    zamok = rezhim == '--primenit'
    if zamok:
        vzyat_zamok('fixKN (контакты КО и метки Битрикса в каталоге КЦ)')
    zapisano = False
    try:
        do_zh = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые до:', do_zh)
        ok = stadiya(paket)
        if rezhim != '--primenit':
            p('сухой прогон: живые файлы и каталог не трогались')
            return
        if not ok:
            p('ПРОВЕРКА НЕ ПРОШЛА – живые файлы не трогались')
            raise SystemExit(1)
        for rel in PRAVIM:
            os.makedirs(os.path.dirname(os.path.join(BEKAP, rel)), exist_ok=True)
            shutil.copy2(os.path.join(KOREN, rel), os.path.join(BEKAP, rel))
            if sha(chitat(os.path.join(KOREN, rel))) != sha(chitat(os.path.join(STAGE, 'do', rel))):
                p('ЖИВОЙ ШАБЛОН ИЗМЕНИЛСЯ ПОСЛЕ КОПИИ В STAGE: %s – запись отменена' % rel)
                raise SystemExit(1)
        kopiya_bazy(KAT, os.path.join(BEKAP, 'centrifugal.db'))
        p('копии прежних (шаблоны, каталог) ->', BEKAP)
        zapisano = True
        p('каталог:', primenit_k_katalogu(KAT, paket))
        p('шаблоны:', pravki_shablonov(KOREN))
        sovp = all(sha(chitat(os.path.join(KOREN, r))) == sha(chitat(os.path.join(STAGE, 'posle', r))) for r in PRAVIM)
        if not sovp:
            raise RuntimeError('живые шаблоны не совпали с проверенным stage')
        plokh = []
        proverit_katalog(os.path.join(BEKAP, 'centrifugal.db'), KAT, paket, plokh)
        if plokh:
            raise RuntimeError('живой каталог: ' + '; '.join(plokh))
        posle = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые после:', posle)
        if posle != do_zh:
            raise RuntimeError('коды ответов изменились: %s -> %s' % (do_zh, posle))
        p('ГОТОВО')
    except Exception as e:  # noqa: BLE001 – после записи любая ошибка = откат
        if not zapisano:
            raise
        p('ОШИБКА ПОСЛЕ ЗАПИСИ: %s – возвращаю шаблоны и каталог из %s' % (e, BEKAP))
        vernut(BEKAP)
        raise SystemExit(1)
    finally:
        if zamok:
            try:
                os.remove(ZAMOK)
            except OSError:
                pass
        io.open(os.path.join(DROP, 'fixKN-%s-%s.txt' % (rezhim.strip('-'), T)), 'w', encoding='utf-8').write('\n'.join(log))
        if os.path.isdir(STAGE):
            shutil.rmtree(STAGE, ignore_errors=True)


if __name__ == '__main__':
    main()
