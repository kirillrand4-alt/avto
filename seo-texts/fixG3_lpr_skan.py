# -*- coding: utf-8 -*-
"""fixG3 (локально): у кого из кандидатов на страницах СВОЕГО сайта есть ЛПР с личным номером (цель
владельца) – разбор подписей агента C (fixC_razbor: razmetka/podpis/fio_i_dolzhnost, lyudi_stranicy) и
роль той же функцией панели (centro_catalog.rol_kontakta). Номер в файле или новый со страницы – всё равно.
Выход: {ИНН: {stupen: 4/3/2/1, lpr: [{k10, dob, fio, dolzh, rol, vid, url, v_fajle}]}}; номера – только в
выходном JSON (scratchpad), печать – без номеров.

    python3 fixG3_lpr_skan.py <kandidaty.json> <chey.json> <папка страниц> <корень с app> <выход.json>
"""
import collections
import gzip
import json
import os
import re
import sys

KAND, CHEY, PAPKA, APP, VYHOD = sys.argv[1:6]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
sys.path.insert(0, APP)
os.environ.setdefault('CENTRIFUGAL_DB', os.path.join(os.path.dirname(os.path.abspath(VYHOD)), 'net.db'))
import fixC_razbor as R  # noqa: E402
from app.services import centro_catalog as cat  # noqa: E402

kand = json.load(open(KAND, encoding='utf-8'))
chey = json.load(open(CHEY, encoding='utf-8'))
indeks = json.load(open(os.path.join(PAPKA, '_indeks.json'), encoding='utf-8'))


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    if any(ord(ch) > 127 for ch in d):
        try:
            d = d.encode('idna').decode('ascii')
        except UnicodeError:
            pass
    return d[4:] if d.startswith('www.') else d


po_domenu = collections.defaultdict(list)
for u, z in indeks.items():
    if z.get('kod') == 200 and z.get('fajl'):
        po_domenu[domen(u)].append(u)
out = {}
for c in kand:
    inn = c['inn']
    sd = (chey.get(inn) or {}).get('sayt_domen') or domen(c['sayt'])
    v_fajle = {R.klyuch10(R.cifry(re.split('доб', n['nomer'])[0])) for n in c['nomera']}
    lpr = []
    vid = set()
    for u in po_domenu.get(sd, []):
        z = indeks[u]
        try:
            t, _ = R.html_v_tekst(R.dekodirovat(gzip.open(os.path.join(PAPKA, z['fajl'])).read(), z.get('tip', '')))
        except Exception:  # noqa: BLE001
            continue
        vh = R.nomera_v_tekste(t)
        rm = R.razmetka(t, vh)
        for i, x in enumerate(vh):
            if not x['k10'] or (x['k10'], x['dob']) in vid:
                continue
            p_, _ = rm.get(i) or R.podpis(t, vh, i)
            fio, dolzh = R.fio_i_dolzhnost(p_)
            rk = cat.rol_kontakta({'value': '+7' + x['k10'], 'position': dolzh})
            if rk['lpr']:
                vid.add((x['k10'], x['dob']))
                lpr.append({'k10': x['k10'], 'dob': x['dob'], 'fio': fio, 'dolzh': dolzh, 'rol': rk['vid'], 'url': u,
                            'vid': cat.vid_nomera_po_cifram('+7' + x['k10'] + (' доб. ' + x['dob'] if x['dob'] else '')),
                            'v_fajle': x['k10'] in v_fajle, 'kak': 'подпись у номера',
                            'okrest': t[max(0, x['nach'] - 160):x['kon'] + 60]})
        for zz in R.lyudi_stranicy(t):
            if not zz['fio'] or not zz['dolzh'] or zz['otzyv']:
                continue
            rk = cat.rol_kontakta({'position': zz['dolzh']})
            if not rk['lpr']:
                continue
            for k10, dob in zz['nomera']:
                if (k10, dob) in vid:
                    continue
                vid.add((k10, dob))
                lpr.append({'k10': k10, 'dob': dob, 'fio': zz['fio'], 'dolzh': zz['dolzh'], 'rol': rk['vid'], 'url': u,
                            'vid': cat.vid_nomera_po_cifram('+7' + k10 + (' доб. ' + dob if dob else '')),
                            'v_fajle': k10 in v_fajle, 'kak': 'запись «должность + ФИО» страницы', 'okrest': zz['tekst']})
    mob = [x for x in lpr if x['vid'] == 'мобильный']
    st = 4 if any(x['fio'] for x in mob) else 3 if mob else 2 if lpr else 1
    out[inn] = {'stupen': st, 'lpr': lpr, 'nazvanie': c['nazvanie'], 'mesto': c['mesto']}
json.dump(out, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('ступени по страницам своих сайтов:', collections.Counter(v['stupen'] for v in out.values()))
for inn, v in sorted(out.items(), key=lambda kv: (-kv[1]['stupen'], kv[1]['mesto'])):
    if v['stupen'] > 1:
        print('  место %3d %s %-34s ступень %d: %s' % (v['mesto'], inn, v['nazvanie'][:34], {4: 800, 3: 600, 2: 400}[v['stupen']],
                                                     '; '.join('%s %s (%s, %s)' % (x['fio'], x['dolzh'][:40], x['rol'], x['vid']) for x in v['lpr'])[:230]))
