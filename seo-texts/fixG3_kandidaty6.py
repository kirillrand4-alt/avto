# -*- coding: utf-8 -*-
"""fixG3 (локально): кандидаты из ОСТАТКА файла 6 Meyer («поиск агентами по узкому списку отраслей») на
добор 8 компаний (владелец 09.10: «добрать недостающие 8 … остаток файла 6, потом файл 2, потом файл 3»).

Строки компаний и номеров – тем же скриптом отбора Базы 6 (meyer_baza6_v_json.py исполняется как есть,
кроме одного: компании без ЛПР и выручкой меньше 1,5 млрд (их вариант А не брал) не пропускаются, а
получают уровень «без ЛПР (остаток файла 6)»). Рейтинг файла – его балл moy_prioritet.
Кандидат: нет в панели (текущий каталог) и не убран из неё (arhiv_company), регион не Воронежская
область, основной ОКВЭД даёт сегмент по okved_segment_tz.json, выручка от 100 млн (верхнего предела нет),
есть хотя бы один номер со страницы домена своего сайта. Порядок: сначала ЛПР с личным номером (роль –
centro_catalog.rol_kontakta по должности/роли файла; ФИО + мобильный, мобильный, рабочий/добавочный),
затем по баллу файла.
Выход – в формате fixG_kandidaty.py (kandidaty.json) + строки загрузчика (meyer-fixG3-f6.json).

    python3 fixG3_kandidaty6.py <baza6.xlsx> <meyer-baza1.json> <каталог.db> <копия app (корень)> <выход-папка>
"""
import collections
import io
import json
import os
import re
import sqlite3
import sys

VHOD, B1, KAT, APP, OUT = sys.argv[1:6]
os.makedirs(OUT, exist_ok=True)
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
sys.path.insert(0, APP)
os.environ.setdefault('CENTRIFUGAL_DB', os.path.join(OUT, 'net.db'))
import fixE1_regiony_segmenty as E1  # noqa: E402
from app.services import centro_catalog as cat  # noqa: E402

TZ = json.load(open(os.path.join(ZDES, 'okved_segment_tz.json'), encoding='utf-8'))
skript = os.path.join(ZDES, 'meyer_baza6_v_json.py')
kod = io.open(skript, encoding='utf-8').read()
STARO = """    else:
        continue
    (sliyanie if inn in inn1 else vybor).append((c, ks, uroven))"""
assert kod.count(STARO) == 1
kod = kod.replace(STARO, """    elif ks:
        uroven = 'без ЛПР (остаток файла 6)'
    else:
        continue
    (sliyanie if inn in inn1 else vybor).append((c, ks, uroven))""")
VSE = os.path.join(OUT, 'meyer-fixG3-f6.json')
sys.argv = [skript, VHOD, B1, VSE]
ns = {'__name__': 'baza6', '__file__': skript}
exec(compile(kod, skript, 'exec'), ns)
d = json.load(open(VSE, encoding='utf-8'))

k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
v_paneli = {r[0] for r in k.execute('SELECT inn FROM company')}
ubrany = {r[0] for r in k.execute('SELECT inn FROM arhiv_company')} if k.execute(
    "SELECT 1 FROM sqlite_master WHERE name='arhiv_company'").fetchone() else set()
NE_SAYTY = ('zakupki.gov.ru', 'tender.pro', 'b2b-center.ru', 'rusprofile', 'checko.ru', 'list-org.com', 'vk.com', 'hh.ru')


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    u = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    return u[4:] if u.startswith('www.') else u


kont = collections.defaultdict(list)
for x in d['kontakty']:
    kont[x['inn']].append(x)
out, otsev = [], collections.Counter()
for c in d['kompanii']:
    inn = c['inn']
    if inn in v_paneli:
        otsev['уже в панели'] += 1
        continue
    if inn in ubrany:
        otsev['убрана из панели 09.10 (пометка/Воронеж)'] += 1
        continue
    reg = E1.region_norm(c['region'])
    vyr = c['vyruchka_rub']
    sd = domen(c['sayt'])
    svoi = [x for x in kont[inn] if sd and x['source_url'] and (domen(x['source_url']) == sd or domen(x['source_url']).endswith('.' + sd))]
    if reg == 'Воронежская область':
        otsev['Воронежская область'] += 1
    elif not E1.po_kodu(c['okved'], TZ):
        otsev['основной ОКВЭД не даёт сегмента'] += 1
    elif not vyr or vyr < 1e8:
        otsev['выручка меньше 100 млн или нет'] += 1
    elif not sd or any(n in sd for n in NE_SAYTY):
        otsev['нет своего сайта'] += 1
    elif not svoi:
        otsev['нет номера со страницы своего сайта'] += 1
    else:
        lpr = []
        for x in svoi:
            rk = cat.rol_kontakta({'value': x['value'], 'position': x['position'], 'role': x['role']})
            if rk['lpr']:
                lpr.append((x, rk))
        mob = [x for x, _ in lpr if cat.vid_nomera_po_cifram(x['value']) == 'мобильный']
        stup = 4 if any(x['person'] for x in mob) else 3 if mob else 2 if lpr else 1
        out.append((stup, c['moy_prioritet'], c, kont[inn], svoi, reg))
print('остаток файла 6: кандидатов %d; отсев: %s' % (len(out), dict(otsev)))
out.sort(key=lambda z: (-z[0], -z[1], z[2]['inn']))
print('по ступени ЛПР:', collections.Counter(z[0] for z in out))
rez = []
for n, (stup, ball, c, ks, svoi, reg) in enumerate(out, 1):
    sd = domen(c['sayt'])
    rez.append({'mesto': n, 'reyting': ball, 'stupen_lpr': stup, 'inn': c['inn'], 'nazvanie': c['predpriyatie'], 'region': reg,
                'okved': c['okved'], 'vyruchka': c['vyruchka_rub'], 'sayt': c['sayt'], 'opisanie': c['opisanie'],
                'segment': c['segment'], 'svyazka': c['sayt_chey'], 'holding_agent': c['holding'],
                'nomera': [{'nomer': x['value'], 'tip': x['phone_type'], 'podpis': x['role'], 'url': x['source_url'] or '',
                            'chya': '', 'istochnik': x['source'], 'fragment': x['fragment'] or '',
                            'svoy': x in svoi, 'nastoyashchiy': x in svoi} for x in ks]})
io.open(os.path.join(OUT, 'kandidaty.json'), 'w', encoding='utf-8').write(json.dumps(rez, ensure_ascii=False, indent=1))
for z in rez[:40]:
    print('  %2d ступ%d %5.1f %s %-30s %-22s %-7s %6.0f млн %s' % (z['mesto'], z['stupen_lpr'], z['reyting'], z['inn'], z['nazvanie'][:30],
                                                             z['region'][:22], z['okved'], (z['vyruchka'] or 0) / 1e6, z['sayt'][:30]))
