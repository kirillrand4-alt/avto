# -*- coding: utf-8 -*-
"""fixE2: правки кода панели Meyer под замком C:\\centro2\\_zamok.txt.

1. Флаги ЛПР после «Получен личный номер ЛПР». Агент B кладёт номер в каталог (contact,
   источник «от продавца»), но флаги компании – lpr_mobilnyy, lpr_s_fio, has_tech, lpr_roli,
   lpr_kratko… – хранятся колонками и не пересчитывались: фильтры «ЛПР с мобильным», «ЛПР с
   ФИО», «Есть техЛПР», роль ЛПР и строка ЛПР в списке оставались прежними. Теперь при
   сохранении результата флаги этой компании считаются заново (та же логика, что пересчёт
   агента C, fixC_kontakty.py шаг 3 – через catalog.contacts), а компания поднимается в свою
   ступень очереди (балл внутри ступени прежний; ступень только растёт; пометку не трогает).
2. «Балл очереди»: подсказки у заголовка списка и в карточке – что значат сотни (ступень), и
   расшифровка балла (prioritet_pochemu) при наведении на число в списке и в карточке.

Порядок: замок → перечитать файлы → правки по якорям (идемпотентно) → проверка в отдельном
venv-процессе на КОПИЯХ баз (рендер, сохранение номера ЛПР, флаги, ступень, фильтры) →
провал: вернуть свои файлы из своей копии этого прогона → успех: перезапуск → отдать замок.

    python3 zapusk_na_servere.py fixE2_kod.py
"""
import io
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
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
T = os.path.join(APP, 'templates')
L = os.path.join(T, '_ochered_spisok.html')
C = os.path.join(T, 'centro.html')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']

RCS_KOD = r'''

# ---------------------------------------------------------------- fixE2: флаги ЛПР после номера от продавца
# Владелец 08.10: после «Получен личный номер ЛПР» номер ложится в каталог (агент B), но флаги
# компании хранятся колонками (их считал агент C скриптом) и не менялись: фильтры «ЛПР с
# мобильным», «ЛПР с ФИО», «Есть техЛПР», роль ЛПР и строка ЛПР в списке оставались прежними.
# Здесь – пересчёт этой одной компании той же логикой (catalog.contacts решает роль и вид
# номера), и подъём в ступень очереди (fixE2): 800 ЛПР с ФИО и мобильным, 600 ЛПР с мобильным,
# 400 ЛПР с рабочим/добавочным, 200 без ЛПР. Ступень только растёт; компания с пометкой
# очереди («нецелевая» / «недействующая») остаётся в конце.
_FIXE2_STUPEN = {4: 800, 3: 600, 2: 400, 1: 200}


def _fixE2_pokaz(v) -> str:
    osn, dob = catalog._razdelit_dobavochnyy(v)
    d = re.sub(r"\D", "", str(osn or ""))
    if len(d) == 11 and d[0] == "7":
        osn = "+7 %s %s-%s-%s" % (d[1:4], d[4:7], d[7:9], d[9:])
    return str(osn or "") + (" доб. " + dob if dob else "")


def _fixE2_pereschet_lpr(inn: str) -> str:
    import sqlite3 as _sq_e2
    inn = sales.normalize_inn(inn)
    items = catalog.contacts(inn)
    tel = [x for x in items if x["kind"] == "phone"]
    lpr = [x for x in tel if x["lpr"]]
    sprosit = [x for x in items if x["kind"] == "sprosit"]
    roli = list(dict.fromkeys(x["rol_vid"] for x in lpr))
    fio_lpr = {catalog._kl_fio(x["person"]) for x in lpr if x["person"]}
    mob = [x for x in lpr if x["vid_nomera"] == "мобильный"]
    if lpr:
        l0 = lpr[0]
        kr = " · ".join(v for v in (l0["person"], l0["position"] or l0["rol_vid"], _fixE2_pokaz(l0["value"])) if v)
        if len(lpr) > 1:
            kr += " (+ ещё %d)" % (len(lpr) - 1)
    elif sprosit:
        s0 = sprosit[0]
        kr = "%s · %s (без номера – спросить у приёмной)" % (s0["person"], s0["position"] or s0["rol_vid"])
    else:
        put_ = [x for x in tel if x["has_role"]]
        if put_:
            p0 = put_[0]
            kr = ("ЛПР не найден, через приёмную: %s" if p0["rol_vid"] in ("приёмная", "общий номер")
                  else "ЛПР не найден, номер с сайта: %s") % _fixE2_pokaz(p0["value"])
            n_mob = sum(1 for x in tel if x["vid_nomera"] == "мобильный")
            if n_mob:
                kr += " (мобильных без ЛПР: %d)" % n_mob
        else:
            kr = "ЛПР не найден" + (", номера только неличные: %d" % len(tel) if tel else ", номеров нет")
    novoe = {"has_tech": int(any(x["is_tech"] for x in lpr)),
             "n_tech": sum(1 for x in lpr if x["is_tech"]),
             "has_purchaser": int(any(x["is_purchaser"] for x in lpr)),
             "n_purchaser": sum(1 for x in lpr if x["is_purchaser"]),
             "lpr_mobilnyy": int(bool(mob)), "lpr_s_fio": len(fio_lpr),
             "lpr_roli": ", ".join(roli), "lpr_kratko": kr,
             "n_phones": len(tel), "has_phone": int(bool(tel))}
    stupen = 4 if any(x["person"] for x in mob) else 3 if mob else 2 if lpr else 1
    put = catalog.db_path()
    pometka = ""
    podnyata = None
    for popytka in range(4):
        try:
            kc = _sq_e2.connect(str(put), timeout=20)
            try:
                kol = {r[1] for r in kc.execute("PRAGMA table_info(company)")}
                if "pometka_ocheredi" in kol:
                    r = kc.execute("SELECT pometka_ocheredi FROM company WHERE inn=?", (inn,)).fetchone()
                    pometka = str((r[0] if r else "") or "").strip()
                # ступень очереди – в базе продаж (только если ступени уже проставлены fixE2)
                if not pometka:
                    with sales.connect() as conn:
                        kol_a = {r[1] for r in conn.execute("PRAGMA table_info(company_assignment)")}
                        if "stupen_ocheredi" in kol_a:
                            a = conn.execute("SELECT assignment_score, stupen_ocheredi FROM company_assignment "
                                             "WHERE inn=?", (inn,)).fetchone()
                            if a and a[1] in _FIXE2_STUPEN and stupen > a[1]:
                                conn.execute(
                                    "UPDATE company_assignment SET assignment_score=?, stupen_ocheredi=?, "
                                    "has_phone=?, has_purchaser=?, has_tech=? WHERE inn=?",
                                    (round(float(a[0] or 0) + _FIXE2_STUPEN[stupen] - _FIXE2_STUPEN[a[1]], 1),
                                     stupen, novoe["has_phone"], novoe["has_purchaser"], novoe["has_tech"], inn))
                                podnyata = (_FIXE2_STUPEN[a[1]], _FIXE2_STUPEN[stupen])
                if podnyata and "prioritet_pochemu" in kol:
                    den = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%d.%m")
                    r = kc.execute("SELECT prioritet_pochemu FROM company WHERE inn=?", (inn,)).fetchone()
                    novoe["prioritet_pochemu"] = (str((r[0] if r else "") or "") +
                                                  " · %s: «Получен личный номер ЛПР» – ступень %d → %d"
                                                  % (den, podnyata[0], podnyata[1])).strip(" ·")
                polya = {k: v for k, v in novoe.items() if k in kol}
                if polya:
                    kc.execute("UPDATE company SET %s WHERE inn=?" % ", ".join("%s=?" % k for k in polya),
                               list(polya.values()) + [inn])
                kc.commit()
            finally:
                kc.close()
            return "флаги ЛПР пересчитаны" + (", ступень %d → %d" % podnyata if podnyata else "")
        except _sq_e2.OperationalError as exc:
            if "locked" in str(exc).lower() and popytka < 3:
                time.sleep(1.5)
                continue
            return "флаги ЛПР не пересчитаны: %s" % str(exc)[:80]
    return "флаги ЛПР не пересчитаны: каталог занят"
'''

VYZOV_STARO = '''            sales.otmetit_katalog(z["id"], cid, itog)
        except Exception:  # noqa: BLE001 – пометка о каталоге не важнее самого номера
            pass
'''
VYZOV_NOVO = VYZOV_STARO + '''        if cid:
            try:
                _fixE2_pereschet_lpr(z["inn"])      # fixE2: флаги ЛПР компании и ступень очереди
            except Exception:  # noqa: BLE001 – пересчёт флагов не важнее самого номера
                pass
'''
PODSKAZKA = ('По нему строится очередь продавца: больше – выше. Сотни – ступень: 800 ЛПР с ФИО и личным '
             'мобильным, 600 ЛПР с личным мобильным, 400 ЛПР с рабочим / добавочным, 200 ЛПР не найден, '
             'меньше 200 – пометка очереди (нецелевая / недействующая, в конце). Внутри ступени – важность '
             'компании (выручка, попадание, лучший контакт, ещё ЛПР, сегменты) и надбавки панели. '
             'Расшифровка – при наведении на число.')


# ====================================================================== ПРОВЕРКА (venv)
def proverka(test_sales, test_kat):
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
    import app
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    ok(os.path.abspath(app.__file__).lower().startswith(APP.lower()), 'код из %s' % APP)
    ok(str(catalog.db_path()) == test_kat and str(sales.sales_db_path()) == test_sales, 'базы – временные копии')
    ok(hasattr(rcs, '_fixE2_pereschet_lpr'), 'в коде есть пересчёт флагов fixE2')
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 2, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    vnutr.dependency_overrides[rcs._same_origin] = lambda: None
    b = sqlite3.connect(test_sales)
    b.row_factory = sqlite3.Row
    kat = sqlite3.connect(test_kat)
    kat.row_factory = sqlite3.Row
    zanyatye = {str(r[0]) for r in b.execute('SELECT inn FROM company_state UNION SELECT inn FROM zvonok_sobytie')}
    pom = {r[0] for r in kat.execute("SELECT inn FROM company WHERE TRIM(COALESCE(pometka_ocheredi,''))<>''")}
    kol_a = {r[1] for r in b.execute('PRAGMA table_info(company_assignment)')}
    est_stupen = 'stupen_ocheredi' in kol_a
    ok(est_stupen, 'ступени очереди в базе продаж проставлены (fixE2_ochered.py)')
    kand = [r['inn'] for r in b.execute("SELECT inn FROM company_assignment WHERE username='meyer2' "
                                        "AND stupen_ocheredi=1 ORDER BY assignment_score DESC")
            if r['inn'] not in zanyatye and r['inn'] not in pom] if est_stupen else []
    rx_row = re.compile(r'<tr data-href="[^"]*centro\?inn=(\d+)[^"]*">.*?class="chislo tiho och-ball"([^>]*)>([-\d.]+)</td>', re.S)

    def chislo(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1
    with TestClient(vnutr) as kl:
        def poluchit(u, kak=ADMIN, **kw):
            kto['u'] = kak
            return kl.get(PUT + u, **kw)
        A = [r['inn'] for r in b.execute("SELECT inn FROM company_assignment WHERE username='meyer2' "
                                         "ORDER BY assignment_score DESC LIMIT 1")]
        for nazv, u, kak, kod in (('главная, админ', '/centro', ADMIN, 200),
                                  ('карточка, админ', '/centro?inn=' + A[0], ADMIN, 200),
                                  ('статистика, админ', '/centro/stats', ADMIN, 200),
                                  ('CSV, админ', '/centro/vygruzka.csv', ADMIN, 200),
                                  ('главная, продавец', '/centro', PROD, 200),
                                  ('карточка, продавец', '/centro?inn=' + A[0], PROD, 200),
                                  ('статистика, продавец', '/centro/stats', PROD, 403)):
            o = poluchit(u, kak)
            ok(o.status_code == kod, '%s: %s' % (nazv, o.status_code))
        t = poluchit('/centro', PROD).text
        ok('Сотни – ступень: 800' in t, 'список: подсказка «Балл очереди» про ступени')
        stroki = rx_row.findall(t)
        ok(stroki and 'title="ступень' in stroki[0][1], 'список: расшифровка балла при наведении на число')
        t = poluchit('/centro?inn=' + A[0], PROD).text
        ok('Сотни – ступень: 800' in t and 'ступень 800' in t, 'карточка: подсказка и расшифровка балла')
        if not kand:
            ok(False, 'нет компании без ЛПР у meyer2 для проверки номера ЛПР')
        else:
            inn = kand[0]
            do_k = dict(kat.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            do_a = dict(b.execute('SELECT * FROM company_assignment WHERE inn=?', (inn,)).fetchone())
            f_do = {f: chislo(poluchit('/centro', PROD, params={f: '1'}).text) for f in ('lpr_mobilnyy', 'lpr_fio', 'has_tech')}
            kto['u'] = PROD
            o = kl.post(PUT + '/centro/save', data={
                'inn': inn, 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов Тест Тестович',
                'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '+7 900 000-00-00', 'comment': 'fixE2-тест'},
                follow_redirects=False)
            ok(o.status_code == 303, 'сохранение «Получен личный номер ЛПР»: %s' % o.status_code)
            po_k = dict(kat.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            po_a = dict(b.execute('SELECT * FROM company_assignment WHERE inn=?', (inn,)).fetchone())
            ok(po_k['lpr_mobilnyy'] == 1 and (po_k['lpr_s_fio'] or 0) >= 1 and po_k['has_tech'] == 1,
               'флаги компании %s: ЛПР мобильный %s→%s, ЛПР с ФИО %s→%s, техЛПР %s→%s' % (
                   inn, do_k['lpr_mobilnyy'], po_k['lpr_mobilnyy'], do_k['lpr_s_fio'], po_k['lpr_s_fio'],
                   do_k['has_tech'], po_k['has_tech']))
            ok('техдиректор / главный инженер' in (po_k['lpr_roli'] or '') and (po_k['lpr_kratko'] or '').startswith('Тестов'),
               'роль и строка ЛПР: «%s» / «%s»' % (po_k['lpr_roli'], (po_k['lpr_kratko'] or '')[:60]))
            ok(po_a['stupen_ocheredi'] == 4 and abs(po_a['assignment_score'] - do_a['assignment_score'] - 600) < 0.05,
               'ступень очереди 200 → 800: балл %.1f → %.1f' % (do_a['assignment_score'], po_a['assignment_score']))
            ok('ступень 200 → 800' in (po_k['prioritet_pochemu'] or ''), 'расшифровка балла дополнена')
            f_po = {f: chislo(poluchit('/centro', PROD, params={f: '1'}).text) for f in ('lpr_mobilnyy', 'lpr_fio', 'has_tech')}
            ok(all(f_po[f] == f_do[f] + 1 for f in f_do), 'фильтры у продавца: %s → %s' % (f_do, f_po))
            t = poluchit('/centro', PROD, params={'size': 100}).text
            st = rx_row.findall(t)
            bally = [float(v) for _, _, v in st]
            ok(all(bally[j] >= bally[j + 1] for j in range(len(bally) - 1)), 'список по-прежнему по убыванию балла')
            ok(any(i == inn for i, _, _ in st[:60]), 'компания поднялась в верх очереди (ступень 800)')
            # повтор того же номера – не дублирует
            o = kl.post(PUT + '/centro/save', data={
                'inn': inn, 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов Тест Тестович',
                'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '+7 900 000-00-00'}, follow_redirects=False)
            po2 = dict(b.execute('SELECT * FROM company_assignment WHERE inn=?', (inn,)).fetchone())
            ok(o.status_code == 303 and po2['assignment_score'] == po_a['assignment_score'], 'повтор номера балл не меняет')
        # «Не дозвонился» ничего не ломает
        if len(kand) > 1:
            kto['u'] = PROD
            o = kl.post(PUT + '/centro/save', data={'inn': kand[1], 'call_result': 'ne_dozvonilsya'}, follow_redirects=False)
            ok(o.status_code == 303, '«Не дозвонился»: %s' % o.status_code)
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    raise SystemExit(1 if proverka(sys.argv[i + 1], sys.argv[i + 2]) else 0)


# ====================================================================== ПРАВКИ ПОД ЗАМКОМ
def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)                      # брошенный (старше 25 мин)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def kopiya(src_put, dst_put):
    src = sqlite3.connect('file:%s?mode=ro' % src_put, uri=True)
    dst = sqlite3.connect(dst_put)
    src.backup(dst)
    dst.close()
    src.close()


VREMYA = time.strftime('%Y%m%d-%H%M%S')
BEKAP = os.path.join(KOREN, '_bekap', 'fixE2-kod-' + VREMYA)
IZMENENY = {}
log = []
nado = sdelano = 0


def pravka(p, staro, novo, imya, priznak):
    global nado, sdelano
    nado += 1
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    n = t.count(staro)
    if n != 1:
        log.append('[ЯКОРЬ: %d] %s – не правлю' % (n, imya))
        return
    b = os.path.join(BEKAP, os.path.basename(p))
    if not os.path.exists(b):
        shutil.copy2(p, b)
        IZMENENY[os.path.basename(p)] = p
    io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    sdelano += 1
    log.append('[ок] ' + imya)


def vernut():
    for imya, kuda in IZMENENY.items():
        shutil.copy2(os.path.join(BEKAP, imya), kuda)


vzyat_zamok('fixE2')
try:
    os.makedirs(BEKAP, exist_ok=True)
    # --- routes_centro_sales: функция в конец файла и вызов после записи номера в каталог
    nado += 1
    t = io.open(RCS, encoding='utf-8').read()
    if 'def _fixE2_pereschet_lpr' in t:
        sdelano += 1
        log.append('[уже] функция пересчёта флагов')
    else:
        shutil.copy2(RCS, os.path.join(BEKAP, 'routes_centro_sales.py'))
        IZMENENY['routes_centro_sales.py'] = RCS
        io.open(RCS, 'w', encoding='utf-8').write(t.rstrip('\n') + '\n' + RCS_KOD)
        sdelano += 1
        log.append('[ок] функция пересчёта флагов')
    pravka(RCS, VYZOV_STARO, VYZOV_NOVO, 'вызов пересчёта после «Получен личный номер ЛПР»',
           '_fixE2_pereschet_lpr(z["inn"])')
    # --- список: подсказка у заголовка и расшифровка у числа
    pravka(L, '<th title="По нему строится очередь продавца: больше – выше">Балл очереди</th>',
           '<th title="%s">Балл очереди</th>' % PODSKAZKA, 'список: подсказка «Балл очереди»', 'Сотни – ступень: 800')
    pravka(L, '''<td class="chislo tiho och-ball">{{ '%.1f'|format(c.assignment_score or 0) }}</td>''',
           '''<td class="chislo tiho och-ball"{% if c.prioritet_pochemu %} title="{{ c.prioritet_pochemu }}"{% endif %}>{{ '%.1f'|format(c.assignment_score or 0) }}</td>''',
           'список: расшифровка балла у числа', 'och-ball"{% if c.prioritet_pochemu %}')
    # --- карточка: подсказка у «Балл очереди»
    pravka(C, 'Балл очереди: по нему строится очередь продавца (больше – выше). Важность предприятия плюс надбавки '
              'за то, что до него есть чем дозвониться: телефон, закупщик, технический человек; поправка по ОКВЭД. '
              'Минус 1000, если юрлицо ликвидировано.',
           'Балл очереди. %s Минус 1000, если юрлицо ликвидировано.{%% if company.prioritet_pochemu %%} '
           'Сейчас: {{ company.prioritet_pochemu }}{%% endif %%}' % PODSKAZKA.replace(' Расшифровка – при наведении на число.', ''),
           'карточка: подсказка «Балл очереди»', 'Сотни – ступень: 800')
    for x in log:
        print('   ' + x)
    print('правок: %d из %d; бэкап своих файлов: %s' % (sdelano, nado, BEKAP))
    if sdelano != nado:
        vernut()
        print('НЕ ВСЕ ПРАВКИ ВНЕСЕНЫ – %d файлов возвращены из своей копии, перезапуска нет' % len(IZMENENY))
        raise SystemExit(1)
    if not IZMENENY:
        print('всё уже было сделано – перезапуск не нужен')
        raise SystemExit(0)
    # --- проверка на копиях баз
    ts, tk = os.path.join(BEKAP, 'test_sales.db'), os.path.join(BEKAP, 'test_kat.db')
    kopiya(os.path.join(KOREN, 'data', 'centro_sales_meyer1.db'), ts)
    kopiya(os.path.join(KOREN, 'data', 'meyer_baza1.db'), tk)
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True,
                       timeout=900, cwd=KOREN, env=sreda)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-4000:]
    for f in (ts, tk):
        try:
            os.remove(f)
        except OSError:
            pass
    io.open(os.path.join(DROP, 'fixE2-kod-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(vyvod)
    uspeh = r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod
    if uspeh and 'routes_centro_sales.py' in IZMENENY:
        p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
        for l in p.stdout.decode('cp866', 'replace').splitlines():
            if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
                subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
        time.sleep(2)
        lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
        lg.write('\n===== перезапуск: fixE2 флаги ЛПР и балл очереди %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
    elif not uspeh:
        vernut()
        print('ПРОВЕРКА НЕ ПРОШЛА – %d своих файлов возвращены из копии, процесс не перезапускался' % len(IZMENENY))
    print('===== ПРОВЕРКА (полностью: fixE2-kod-proverka-%s.txt на дропе) =====' % VREMYA)
    sys.stdout.write(vyvod[-4000:])
finally:
    otdat_zamok()
