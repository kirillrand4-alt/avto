# -*- coding: utf-8 -*-
r"""fixD: запись в каталог Meyer (C:\centro2\data\meyer_baza1.db) – «чей сайт», описания, холдинги.

Входы (дроп): fixD-plan-sayt.json (метки контактов, сайт и «чей сайт» компаний),
fixD-plan-opis.json (описания), fixD-plan-hold.json (холдинги). Готовятся локально
(fixD_plan.py, fixD_opisaniya.py, fixD_holdingi.py) по копии каталога и скачанным страницам.

Что пишется (одной транзакцией, ничего не удаляется):
  contact.chuzhoy_istochnik / chuzhoy_dokaz – «с сайта другого юрлица: …» и чем доказано (новые колонки);
  company.sayt (прежний – в sayt_ishodnyy), sayt_chey (прежний – в sayt_chey_ishodnyy), proverka_sayta
  (свой / группа / чужой / не определено / нет сайта);
  company.opisanie / produkciya / moshchnosti (прежние – в opisanie_ishodnoe / produkciya_ishodnaya /
  moshchnosti_ishodnye);
  company.holding / holding_gruppa (прежние – в holding_ishodnyy / holding_gruppa_ishodnaya);
  holding_chlen: прежние строки не удаляются – группа переименовывается в «snyato0810-<прежняя>»,
  новые группы «gD-…» вставляются (повторный прогон заменяет только свои gD-строки).
Значение пишется, только если в живой базе стоит то же, что было в копии при подготовке плана
(иначе его успел поменять кто-то другой – пропуск и запись в журнал).
Журнал «было → стало» – на дроп: fixD-zhurnal-<время>.json. Копия базы до записи –
C:\centro2\_bekap\fixD-<время>\ (назад целиком НЕ возвращается – откат по журналу).
Код панели и назначения продавцам не трогаются, перезапуска нет.

    3s_fixD_zapis.py [--suhoy] | --proverka
"""
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
PUT = '/obzvon-meyer'
VREMYA = time.strftime('%Y%m%d-%H%M%S')

NOVYE_KOLONKI = {
    'contact': ['chuzhoy_istochnik', 'chuzhoy_dokaz'],
    'company': ['sayt_ishodnyy', 'sayt_chey_ishodnyy', 'proverka_sayta', 'opisanie_ishodnoe', 'produkciya_ishodnaya',
                'moshchnosti_ishodnye', 'holding_ishodnyy', 'holding_gruppa_ishodnaya'],
}
ISHODNOE = {'sayt': 'sayt_ishodnyy', 'sayt_chey': 'sayt_chey_ishodnyy', 'opisanie': 'opisanie_ishodnoe',
            'produkciya': 'produkciya_ishodnaya', 'moshchnosti': 'moshchnosti_ishodnye', 'holding': 'holding_ishodnyy',
            'holding_gruppa': 'holding_gruppa_ishodnaya'}

PRIMERY = {
    'chuzhoy': ['4238013194', '7451451200', '3623007585', '6670358360', '2117003127', '2441000946'],
    'opisanie': ['7720802226', '1021505406', '4238013194', '1101097174'],
    'holding': [('2130181577', '6453143086'), ('3254002818', '3257061868'), ('0306229126', '7224031400'),
                ('2502001403', '6501275085'), ('9721130309', '9725186398'), ('3115006100', '3115006491'),
                ('1101097174', '1105025727')],
    'sayt': [('7205027920', 'aminosib.ru'), ('2441000946', 'fortuna-agrohpp.ru')],
}


def zagruzit(imya):
    return json.load(io.open(os.path.join(DROP, imya), encoding='utf-8'))


def pust(v):
    return '' if v is None else v


if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from app.services import centro_catalog as catalog
    from fastapi.testclient import TestClient
    import html as H
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    k.row_factory = sqlite3.Row
    # числа по базам
    sv = {}
    for r in k.execute('select bazy, proverka_sayta from company'):
        for b in (r['bazy'] or 'без базы').split(' | '):
            sv.setdefault(b, {}).setdefault(r['proverka_sayta'] or '–', 0)
            sv[b][r['proverka_sayta'] or '–'] += 1
    pom = {}
    for r in k.execute("select c.bazy, count(*) n, count(distinct t.inn) k from contact t join company c on c.inn=t.inn "
                       "where coalesce(t.chuzhoy_istochnik,'')<>'' group by c.bazy"):
        for b in (r['bazy'] or '').split(' | '):
            pom.setdefault(b, [0, 0])
            pom[b][0] += r['n']
            pom[b][1] += r['k']
    print('   «чей сайт» по базам: %s' % json.dumps(sv, ensure_ascii=False))
    print('   помечено чужих номеров по базам [номеров, компаний]: %s' % json.dumps(pom, ensure_ascii=False))
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}

    def tekst(html):
        t = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
        return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', t)))

    with TestClient(vnutr) as kl:
        for inn in PRIMERY['chuzhoy']:
            kk = catalog.contacts(inn)
            met = [c for c in kk if (c.get('chuzhoy_istochnik') or '').strip()]
            o = kl.get(PUT + '/centro?inn=' + inn)
            vidno = sum(1 for c in met if (c['chuzhoy_istochnik'][:40] in H.unescape(o.text)))
            ok(o.status_code == 200 and met, 'карточка %s: %s; контактов %d, с меткой в данных %d (%s…); метка в HTML у %d '
               '(вывод метки – правка шаблона/кода агентов A/C)' % (inn, o.status_code, len(kk), len(met),
                                                                   met[0]['chuzhoy_istochnik'][:70] if met else '', vidno))
        for inn in PRIMERY['opisanie']:
            c = k.execute('select opisanie, opisanie_ishodnoe from company where inn=?', (inn,)).fetchone()
            o = kl.get(PUT + '/centro?inn=' + inn)
            t = tekst(o.text)
            ok(o.status_code == 200 and c['opisanie'] and c['opisanie'][:60] in t and c['opisanie_ishodnoe'],
               'описание %s: «%s…» в карточке; прежнее сохранено (%d зн.)' % (inn, c['opisanie'][:70], len(c['opisanie_ishodnoe'] or '')))
        for a, b in PRIMERY['holding']:
            ga = k.execute('select holding, holding_gruppa from company where inn=?', (a,)).fetchone()
            gb = k.execute('select holding, holding_gruppa from company where inn=?', (b,)).fetchone()
            ta, tb = tekst(kl.get(PUT + '/centro?inn=' + a).text), tekst(kl.get(PUT + '/centro?inn=' + b).text)
            sost = [r[0] for r in k.execute('select inn from holding_chlen where gruppa=? order by inn', (ga['holding_gruppa'],))]
            ok(ga['holding_gruppa'] and ga['holding_gruppa'] == gb['holding_gruppa'] and ('Холдинг: ' + ga['holding']) in ta
               and ('Холдинг: ' + gb['holding']) in tb and a in tb and b in ta,
               'холдинг %s ↔ %s: группа %s «%s», состав %s; блок виден с обеих сторон' % (a, b, ga['holding_gruppa'], ga['holding'], sost))
        for inn, dom in PRIMERY['sayt']:
            o = kl.get(PUT + '/centro?inn=' + inn)
            t = tekst(o.text)
            ok('сайт компании · ' + dom in t, 'подпись источника %s: «сайт компании · %s» %s; «сторонний сайт · %s» %s' % (
                inn, dom, 'есть' if 'сайт компании · ' + dom in t else 'НЕТ', dom, 'есть' if 'сторонний сайт · ' + dom in t else 'нет'))
        for rol, pol in (('admin', {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}),
                         ('sales', {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1})):
            vnutr.dependency_overrides[rcs.current_user] = lambda p=pol: p
            for adr in ('/centro', '/centro/stats'):
                o = kl.get(PUT + adr)
                ok(o.status_code in ((200,) if rol == 'admin' or adr == '/centro' else (200, 403)), '%s %s: %s' % (rol, adr, o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    raise SystemExit(1 if plohih[0] else 0)

# ====================================================================== ЗАПИСЬ
SUHOY = '--suhoy' in sys.argv
ps = zagruzit('fixD-plan-sayt.json')
po = zagruzit('fixD-plan-opis.json')
ph = zagruzit('fixD-plan-hold.json')
snimok = zagruzit('fixD-plan-snimok.json')  # значения копии каталога, по которой строился план


def svyaz(put):
    for i in range(30):
        try:
            k = sqlite3.connect(put, timeout=30)
            k.row_factory = sqlite3.Row
            return k
        except sqlite3.OperationalError:
            time.sleep(2)
    raise SystemExit('база не открывается')


k = svyaz(KAT)
zhurnal = []
propuski = []
kol = {t: [r[1] for r in k.execute('pragma table_info(%s)' % t)] for t in ('company', 'contact')}
komp = {r['inn']: dict(r) for r in k.execute('select * from company')}
kont = {r['id']: dict(r) for r in k.execute('select * from contact')}

izm_c = {}   # inn -> {kolonka: novoe}


def postavit(inn, pole, novoe, ozhid):
    """company.pole := novoe, если в живой базе то же, что было в копии (ozhid)."""
    tek = komp[inn].get(pole)
    if pust(tek) != pust(ozhid):
        propuski.append({'inn': inn, 'pole': pole, 'v_kopii': ozhid, 'seychas': tek, 'hotel': novoe})
        return
    if pust(tek) == pust(novoe):
        return
    izm_c.setdefault(inn, {})[pole] = novoe
    ish = ISHODNOE.get(pole)
    if ish and not (komp[inn].get(ish) or '') and pust(tek):
        izm_c[inn][ish] = tek


# 1. «чей сайт» компаний
for inn, p in ps['kompanii'].items():
    if inn not in komp:
        continue
    s = snimok.get(inn, {})
    postavit(inn, 'sayt_chey', p['sayt_chey'], s.get('sayt_chey'))
    izm_c.setdefault(inn, {})['proverka_sayta'] = p['verdikt']
    if 'sayt' in p:
        postavit(inn, 'sayt', p['sayt'], s.get('sayt'))
# 2. описания
for inn, p in po.items():
    if inn not in komp:
        continue
    for pole, nov in p['novoe'].items():
        postavit(inn, pole, nov, p['bylo'][pole])
# 3. холдинги – поля компаний
for inn, p in ph['kompanii'].items():
    if inn not in komp:
        continue
    for pole, nov in p['novoe'].items():
        postavit(inn, pole, nov, p['bylo'][pole])
# 4. метки контактов
izm_k = {}
for kid, p in ps['kontakty'].items():
    kid = int(kid)
    t = kont.get(kid)
    if not t:
        propuski.append({'kontakt': kid, 'pochemu': 'контакта нет в живой базе'})
        continue
    tek = (t.get('chuzhoy_istochnik') or '') if 'chuzhoy_istochnik' in t else ''
    if tek and tek != p['chuzhoy_istochnik']:
        propuski.append({'kontakt': kid, 'pochemu': 'уже стоит другая метка', 'seychas': tek})
        continue
    if tek == p['chuzhoy_istochnik']:
        continue
    izm_k[kid] = p
izm_c = {i: v for i, v in izm_c.items() if v}
print('план: компаний с правками %d (полей %d), контактов с меткой %d, строк холдингов %d; пропусков (поле изменено другими) %d' % (
    len(izm_c), sum(len(v) for v in izm_c.values()), len(izm_k), len(ph['stroki']), len(propuski)))
sch = {}
for v in izm_c.values():
    for p in v:
        sch[p] = sch.get(p, 0) + 1
print('по полям:', json.dumps(sch, ensure_ascii=False))
if propuski:
    print('пропуски:', json.dumps(propuski[:10], ensure_ascii=False)[:1500])
if SUHOY:
    raise SystemExit(0)

B = os.path.join(KOREN, '_bekap', 'fixD-' + VREMYA)
os.makedirs(B, exist_ok=True)
kop = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(kop)
kop.close()
print('копия каталога:', B)
for popytka in range(10):
    try:
        with k:
            for t, kk in NOVYE_KOLONKI.items():
                for c in kk:
                    if c not in kol[t]:
                        k.execute('ALTER TABLE %s ADD COLUMN %s TEXT' % (t, c))
                        zhurnal.append({'tablica': t, 'dobavlena_kolonka': c})
            for inn, v in izm_c.items():
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('%s=?' % p for p in v), list(v.values()) + [inn])
                for p, nov in v.items():
                    zhurnal.append({'tablica': 'company', 'inn': inn, 'pole': p, 'bylo': komp[inn].get(p), 'stalo': nov})
            for kid, p in izm_k.items():
                k.execute('UPDATE contact SET chuzhoy_istochnik=?, chuzhoy_dokaz=? WHERE id=?',
                          (p['chuzhoy_istochnik'], p['chuzhoy_dokaz'], kid))
                zhurnal.append({'tablica': 'contact', 'id': kid, 'inn': kont[kid]['inn'], 'pole': 'chuzhoy_istochnik',
                                'bylo': kont[kid].get('chuzhoy_istochnik'), 'stalo': p['chuzhoy_istochnik'], 'dokaz': p['chuzhoy_dokaz']})
            # холдинги: прежние группы не удаляются – переименовываются; свои gD- заменяются
            stary = [dict(r) for r in k.execute("select * from holding_chlen where gruppa not like 'gD-%' and gruppa not like 'snyato%'")]
            for r in stary:
                zhurnal.append({'tablica': 'holding_chlen', 'inn': r['inn'], 'pole': 'gruppa', 'bylo': r['gruppa'], 'stalo': 'snyato0810-' + r['gruppa']})
            k.execute("update holding_chlen set gruppa='snyato0810-'||gruppa where gruppa not like 'gD-%' and gruppa not like 'snyato%'")
            k.execute("delete from holding_chlen where gruppa like 'gD-%'")  # только свои строки прошлого прогона
            for s in ph['stroki']:
                k.execute('insert into holding_chlen (gruppa, inn, nazvanie, region, segment, vyruchka_rub, v_vybore, svyaz) '
                          'values (?,?,?,?,?,?,?,?)', (s['gruppa'], s['inn'], s['nazvanie'], s['region'], s['segment'],
                                                      s['vyruchka_rub'], s['v_vybore'], s['svyaz']))
                zhurnal.append({'tablica': 'holding_chlen', 'inn': s['inn'], 'pole': 'vstavlena', 'stalo': s})
            # проверка до commit
            n1 = k.execute("select count(*) from contact where coalesce(chuzhoy_istochnik,'')<>''").fetchone()[0]
            gr = k.execute("select count(distinct holding_gruppa) from company where holding_gruppa like 'gD-%'").fetchone()[0]
            nesim = k.execute("select count(*) from company c where holding_gruppa like 'gD-%' and not exists "
                              "(select 1 from holding_chlen h where h.gruppa=c.holding_gruppa and h.inn=c.inn)").fetchone()[0]
            nesim2 = k.execute("select count(*) from holding_chlen h where gruppa like 'gD-%' and exists "
                               "(select 1 from company c where c.inn=h.inn and coalesce(c.holding_gruppa,'')<>h.gruppa)").fetchone()[0]
            print('до commit: контактов с меткой %d, групп у компаний %d, несимметричных %d/%d' % (n1, gr, nesim, nesim2))
            if nesim or nesim2:
                raise RuntimeError('несимметричный холдинг – откат')
        break
    except sqlite3.OperationalError as e:
        if 'locked' in str(e) and popytka < 9:
            print('база занята, повтор через 5 с')
            zhurnal = []
            time.sleep(5)
            continue
        raise
k.close()
io.open(os.path.join(DROP, 'fixD-zhurnal-%s.json' % VREMYA), 'w', encoding='utf-8').write(
    json.dumps({'vremya': VREMYA, 'kopiya': B, 'izmeneniya': zhurnal, 'propuski': propuski}, ensure_ascii=False, indent=0))
print('записано; журнал: fixD-zhurnal-%s.json (%d строк)' % (VREMYA, len(zhurnal)))
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True, timeout=1200, cwd=KOREN,
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-2500:])
    print('ПРОВЕРКА НЕ ПРОШЛА – данные остаются, откат по журналу при необходимости (fixD_otkat.py)')
    raise SystemExit(1)
print('ГОТОВО')
