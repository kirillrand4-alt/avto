# -*- coding: utf-8 -*-
"""fixG (локально): номера кандидатов – стоит ли номер сейчас на странице СВОЕГО сайта, его подпись
(ФИО, должность – разбор агента C: fixC_razbor.razmetka/podpis/fio_i_dolzhnost), вид и роль
(centro_catalog.rol_kontakta и vid_nomera_po_cifram из копии кода панели), люди страницы без
телефона (ЛПР «спросить у приёмной», как у C: fixC_razbor.lyudi_stranicy).

    python3 fixG_nomera.py <kandidaty.json> <chey.json> <папка-страниц> <копия app> <выход.json> ИНН[,ИНН...]
"""
import gzip
import json
import os
import re
import sys

KAND, CHEY, PAPKA, APP, VYHOD, SPISOK = sys.argv[1:7]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
sys.path.insert(0, os.path.dirname(os.path.abspath(APP)))
os.environ.setdefault('CENTRIFUGAL_DB', os.path.join(os.path.dirname(os.path.abspath(VYHOD)), 'net.db'))
import fixC_razbor as R  # noqa: E402
from app.services import centro_catalog as cat  # noqa: E402

kand = {c['inn']: c for c in json.load(open(KAND, encoding='utf-8'))}
chey = json.load(open(CHEY, encoding='utf-8'))
indeks = json.load(open(os.path.join(PAPKA, '_indeks.json'), encoding='utf-8'))
_kesh = {}


def stranica(url):
    if url in _kesh:
        return _kesh[url]
    z = indeks.get(url) or {}
    res = None
    if z.get('fajl') and z.get('kod') == 200 and os.path.exists(os.path.join(PAPKA, z['fajl'])):
        b = gzip.open(os.path.join(PAPKA, z['fajl'])).read()
        h = R.dekodirovat(b, z.get('tip', ''))
        t, komm = R.html_v_tekst(h)
        vh = R.nomera_v_tekste(t)
        res = {'url': url, 't': t, 'komm': komm, 'vh': vh, 'rm': R.razmetka(t, vh)}
    _kesh[url] = res
    return res


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    return d[4:] if d.startswith('www.') else d


def k10(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return R.klyuch10(R.cifry(osn)), dob


out = {}
for inn in SPISOK.split(','):
    c = kand[inn]
    x = chey[inn]
    sd = x['sayt_domen']
    svoi = {d for d, v in x['domeny'].items() if v['verdikt'] == 'свой'}
    stranicy_domena = [u for u, z in indeks.items() if domen(u) == sd and z.get('kod') == 200]
    rez = {'inn': inn, 'nazvanie': c['nazvanie'], 'sayt_domen': sd, 'svoi_domeny': sorted(svoi), 'nomera': [], 'lyudi': []}
    for n in c['nomera']:
        kk, dob = k10(n['nomer'])
        d = domen(n['url'])
        svoy_dom = bool(d) and (d == sd or d.endswith('.' + sd)) and sd in svoi
        # где номер виден сейчас: страница-источник, затем все страницы своего домена
        nashli = []
        for u in [n['url']] + [u for u in stranicy_domena if u != n['url']]:
            st = stranica(u)
            if not st:
                continue
            for i, v in enumerate(st['vh']):
                if v['k10'] == kk and kk:
                    podp, kak = st['rm'].get(i) or R.podpis(st['t'], st['vh'], i)
                    fio, dolzh = R.fio_i_dolzhnost(podp)
                    nashli.append({'url': u, 'tel': v['tel'], 'dob': v['dob'], 'podp': podp[-200:], 'kak': kak, 'fio': fio,
                                   'dolzh': dolzh, 'okrest': st['t'][max(0, v['nach'] - 160):v['kon'] + 80]})
            if nashli and u == n['url']:
                break
        vidimye = [z for z in nashli if not z['tel']]
        luchshiy = None
        for z in (vidimye or nashli):
            if z['fio'] or z['dolzh']:
                luchshiy = z
                break
        luchshiy = luchshiy or ((vidimye or nashli) or [None])[0]
        rk = cat.rol_kontakta({'value': n['nomer'], 'position': (luchshiy or {}).get('dolzh') or '', 'role': n['podpis']})
        rez['nomera'].append({'nomer': n['nomer'], 'tip_fajla': n['tip'], 'podpis_fajla': n['podpis'], 'url': n['url'],
                              'domen': d, 'svoy_domen': svoy_dom, 'nastoyashchiy_b3': n['nastoyashchiy'], 'svoy_b3': n['svoy'],
                              'na_stranice': bool(nashli), 'vidim': bool(vidimye), 'vid_po_cifram': cat.vid_nomera_po_cifram(n['nomer']),
                              'luchshiy': luchshiy, 'vhozhdeniy': len(nashli), 'rol': rk['vid'], 'lpr': rk['lpr'],
                              'fragment_fajla': n['fragment'][:300]})
    # люди страниц своего домена (запись «должность + ФИО»), как у C
    vidali = set()
    for u in stranicy_domena:
        st = stranica(u)
        if not st:
            continue
        for z in R.lyudi_stranicy(st['t']):
            if not z['fio'] or not z['dolzh'] or z['otzyv'] or len(z['fio'].split()) < 2:
                continue
            kl = (z['fio'], z['dolzh'])
            if kl in vidali:
                continue
            vidali.add(kl)
            rk = cat.rol_kontakta({'position': z['dolzh']})
            rez['lyudi'].append({'fio': z['fio'], 'dolzh': z['dolzh'], 'rol': rk['vid'], 'lpr': rk['lpr'], 'url': u,
                                 'nomera': z['nomera'], 'korotkie': z['korotkie'], 'pochta': z['pochta'], 'tekst': z['tekst'][:300]})
    out[inn] = rez
json.dump(out, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for inn, rz in out.items():
    print('=' * 100)
    print(inn, rz['nazvanie'], rz['sayt_domen'], 'свои домены:', rz['svoi_domeny'])
    for n in rz['nomera']:
        l = n['luchshiy'] or {}
        print('  %-18s %-9s файл:%-14s свой_дом:%d наст_b3:%d на_стр:%d вид:%-10s | ФИО: %s | должн: %s | роль: %s%s' % (
            n['nomer'], n['tip_fajla'][:9], n['podpis_fajla'][:14], n['svoy_domen'], n['nastoyashchiy_b3'], n['na_stranice'],
            n['vid_po_cifram'], l.get('fio', ''), (l.get('dolzh') or '')[:40], n['rol'], ' ЛПР' if n['lpr'] else ''))
        if l:
            print('        подпись: %r | %s' % ((l.get('podp') or '')[-90:], l.get('url')))
    for p in rz['lyudi']:
        print('  ЧЕЛОВЕК: %s – %s (%s%s) номера %s местные %s' % (p['fio'], p['dolzh'][:50], p['rol'], ' ЛПР' if p['lpr'] else '',
                                                                p['nomera'], p['korotkie']))
