# -*- coding: utf-8 -*-
r"""fixR 13.10: пересчёт флагов ЛПР у компаний с номерами Беларуси (+375) после правки кода (fixR_kod.py).

Та же логика, что _fixE2_pereschet_lpr (routes_centro_sales.py): catalog.contacts решает роль и вид номера,
отсюда has_tech / n_tech / has_purchaser / n_purchaser / lpr_mobilnyy / lpr_s_fio / lpr_roli / lpr_kratko /
n_phones / has_phone в company (каталог). Прежние значения – в новой колонке company.bylo_fixR (JSON, первая
запись не затирается) и в журнале на дропе. Назначения (company_assignment) этот скрипт НЕ трогает: ступень и
балл очереди у всех ставит общий пересчёт fixR_ball.py --tolko-ball (формула fixF2/fixK), менеджеры не меняются.
Отличие от _fixE2_pereschet_lpr: в prioritet_pochemu не пишется «Получен личный номер ЛПР» (это не он).

    python3 zapusk_na_servere.py fixR_pereschet.py --suho      # посчитать, ничего не писать
    python3 zapusk_na_servere.py fixR_pereschet.py --primenit
"""
import collections
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
VREMYA = time.strftime('%Y%m%d-%H%M%S')
STUPEN = {4: 800, 3: 600, 2: 400, 1: 200, 0: 0}

if '--vnutri' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1650, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5900:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)

suhoy = '--primenit' not in sys.argv
sys.path.insert(0, KOREN)
import zapusk  # noqa: F401,E402  – .env в окружение
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
assert os.path.normcase(os.environ.get('CENTRIFUGAL_DB', '')) == os.path.normcase(KAT)
assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)
from app.services import centro_catalog as cat  # noqa: E402
from app.api import routes_centro_sales as rcs  # noqa: E402
assert hasattr(cat, 'nomer_rb'), 'код fixR не стоит'


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


def flagi(inn):
    """Копия расчёта _fixE2_pereschet_lpr (без записи)."""
    items = cat.contacts(inn)
    tel = [x for x in items if x["kind"] == "phone"]
    lpr = [x for x in tel if x["lpr"]]
    sprosit = [x for x in items if x["kind"] == "sprosit"]
    roli = list(dict.fromkeys(x["rol_vid"] for x in lpr))
    fio_lpr = {cat._kl_fio(x["person"]) for x in lpr if x["person"]}
    mob = [x for x in lpr if x["vid_nomera"] == "мобильный"]
    if lpr:
        l0 = ([x for x in mob if x["person"]] or mob or lpr)[0]
        kr = " · ".join(v for v in (l0["person"], l0["position"] or l0["rol_vid"], rcs._fixE2_pokaz(l0["value"])) if v)
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
                  else "ЛПР не найден, номер с сайта: %s") % rcs._fixE2_pokaz(p0["value"])
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
    n_rb = sum(1 for x in tel if cat.nomer_rb(x["value"]))
    n_rb_mob_lpr = sum(1 for x in mob if cat.nomer_rb(x["value"]))
    return novoe, stupen, n_rb, n_rb_mob_lpr


k = sqlite3.connect(KAT, timeout=30)
k.row_factory = sqlite3.Row
k.execute('PRAGMA busy_timeout=30000')
kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
komp = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
rb_inn = {r[0] for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone'") if cat.nomer_rb(r[1])}
by_inn = {i for i, c in komp.items() if str(c.get('strana') or '') == 'Беларусь' or len(str(i)) == 9}
nabor = sorted((rb_inn | by_inn) & set(komp))
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
s.row_factory = sqlite3.Row
nazn = {r['inn']: dict(r) for r in s.execute('SELECT inn, username, stupen_ocheredi, assignment_score FROM company_assignment')}
s.close()
print('компаний с номерами РБ: %d; белорусских: %d; к пересчёту: %d' % (len(rb_inn), len(by_inn), len(nabor)))

zhurnal = {'vremya': VREMYA, 'suhoy': suhoy, 'kompanii': []}
POLYA = None
izm = 0
plan = {}
for inn in nabor:
    novoe, stupen, n_rb, n_rb_mob = flagi(inn)
    polya = [p for p in novoe if p in kol]
    POLYA = POLYA or polya
    bylo = {p: komp[inn].get(p) for p in polya}
    stalo = {p: novoe[p] for p in polya}
    a = nazn.get(inn) or {}
    plan[inn] = (stalo, bylo)
    zhurnal['kompanii'].append({
        'inn': inn, 'nazvanie': komp[inn].get('predpriyatie') or '', 'strana': komp[inn].get('strana') or '',
        'menedzher': a.get('username'), 'stupen_do': a.get('stupen_ocheredi'), 'ball_do': a.get('assignment_score'),
        'stupen_po_kontaktam': stupen, 'pometka': komp[inn].get('pometka_ocheredi') or '',
        'nomerov_rb': n_rb, 'lpr_na_mobilnom_rb': n_rb_mob, 'bylo': bylo, 'stalo': stalo,
        'izmenilos': sorted(p for p in polya if str(bylo[p]) != str(stalo[p]))})
    if any(str(bylo[p]) != str(stalo[p]) for p in polya):
        izm += 1

sch = collections.Counter()
for z in zhurnal['kompanii']:
    sch[(z['menedzher'], STUPEN.get(z['stupen_do'], z['stupen_do']), STUPEN[z['stupen_po_kontaktam']])] += 1
print('флаги меняются у %d из %d; колонки: %s' % (izm, len(nabor), ', '.join(POLYA or [])))
print('(менеджер, ступень сейчас, ступень по контактам): ' + '; '.join('%s %s->%s: %d' % (a, b, c, n) for (a, b, c), n in sorted(sch.items(), key=str)))
pole = collections.Counter(p for z in zhurnal['kompanii'] for p in z['izmenilos'])
print('какие флаги меняются: %s' % dict(pole))

if not suhoy:
    bekap = os.path.join(KOREN, '_bekap', 'fixR-pereschet-' + VREMYA)
    os.makedirs(bekap, exist_ok=True)
    kopiya(KAT, os.path.join(bekap, 'meyer_baza1.db'))
    kopiya(SALES, os.path.join(bekap, 'centro_sales_meyer1.db'))
    zhurnal['bekap'] = bekap
    print('копии баз (не для отката целиком): %s' % bekap)
    if 'bylo_fixR' not in kol:
        k.execute('ALTER TABLE company ADD COLUMN bylo_fixR TEXT')
        k.commit()
    for popytka in range(10):
        try:
            k.execute('BEGIN IMMEDIATE')
            break
        except sqlite3.OperationalError:
            time.sleep(3)
    else:
        raise SystemExit('каталог занят')
    try:
        n = 0
        for inn, (stalo, bylo) in plan.items():
            if all(str(bylo[p]) == str(stalo[p]) for p in stalo):
                continue
            cur = k.execute('UPDATE company SET %s, bylo_fixR=COALESCE(bylo_fixR, ?) WHERE inn=?'
                            % ', '.join('%s=?' % p for p in stalo),
                            list(stalo.values()) + [json.dumps(dict(bylo, kogda='fixR ' + VREMYA), ensure_ascii=False), inn])
            if cur.rowcount != 1:
                raise RuntimeError('не записалось: %s' % inn)
            n += 1
        # контроль внутри транзакции
        for inn, (stalo, bylo) in plan.items():
            r = k.execute('SELECT %s FROM company WHERE inn=?' % ', '.join(stalo), (inn,)).fetchone()
            if [str(x) for x in r] != [str(v) for v in stalo.values()]:
                raise RuntimeError('контроль: %s не совпало' % inn)
        k.commit()
        print('каталог: флаги ЛПР записаны у %d компаний' % n)
    except BaseException:
        k.rollback()
        raise
k.close()
put = os.path.join(DROP, 'fixR-pereschet-zhurnal-%s%s.json' % (VREMYA, '-suho' if suhoy else ''))
io.open(put, 'w', encoding='utf-8').write(json.dumps(zhurnal, ensure_ascii=False, indent=1))
print('журнал: %s' % os.path.basename(put))
