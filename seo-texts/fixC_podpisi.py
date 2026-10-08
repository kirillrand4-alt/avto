# -*- coding: utf-8 -*-
"""fixC: подписи номеров по страницам-источникам (локально, без записи в каталог).

Вход: копия каталога (fixC-katalog.zip с дропа) и скачанные страницы (fixC-stranicy.zip).
Выход: JSON с предложениями по каждому контакту — ФИО, должность, добавочный, вид номера,
видимый номер вместо битой ссылки tel:, номера из закомментированного HTML, ЛПР без
телефона и новые номера со страниц (люди на общем номере с разными добавочными).
Сам ничего не пишет: решения применяет fixC_kontakty.py на сервере.

    python3 fixC_podpisi.py <каталог.db> <папка страниц> <выход.json>
"""
import collections
import hashlib
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixC_razbor as R  # noqa: E402

_KOD = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixC_klass_kod.py'), encoding='utf-8').read()
_ns = {'re': re}


def _razdelit_dobavochnyy(raw):
    t = str(raw or '').strip()
    m = re.search(r'\s*(?:доб\.?|доп\.?|вн\.?|ext\.?|#)\s*(\d{1,6})\s*$', t, re.I)
    return (t[:m.start()].strip(), m.group(1)) if m else (t, '')


_ns['_razdelit_dobavochnyy'] = _razdelit_dobavochnyy
exec(compile(_KOD, 'fixC_klass_kod.py', 'exec'), _ns)
rol_kontakta = _ns['rol_kontakta']
vid_po_tekstu = _ns['vid_po_tekstu']
vid_nomera_po_cifram = _ns['vid_nomera_po_cifram']


def k10_iz_value(v):
    osn, dob = _razdelit_dobavochnyy(v)
    d = R.cifry(osn)
    return R.klyuch10(d), dob


def zagruzit_stranicy(papka):
    meta = json.load(open(os.path.join(papka, 'meta.json'), encoding='utf-8'))
    kesh = {}

    def tekst(url):
        if url in kesh:
            return kesh[url]
        m = meta.get(url)
        res = None
        if m and m.get('fajl') and os.path.exists(os.path.join(papka, m['fajl'])):
            b = open(os.path.join(papka, m['fajl']), 'rb').read()
            h = R.dekodirovat(b, m.get('ct', ''))
            t, komm = R.html_v_tekst(h)
            vh = R.nomera_v_tekste(t)
            res = {'t': t, 'komm': komm, 'vh': vh, 'rm': R.razmetka(t, vh)}
        kesh[url] = res
        return res
    return tekst


def fragment_kak_tekst(fr):
    # во фрагменте каталога ссылки записаны «[tel:…]» – приводим к меткам разборщика
    t = re.sub(r'\[tel:([^\]]*)\]', lambda m: ' ⟦tel:%s⟧ ' % m.group(1), fr or '')
    vh = R.nomera_v_tekste(t)
    return {'t': t, 'komm': '', 'vh': vh, 'rm': R.razmetka(t, vh)}


def razobrat_vhozhdeniya(st, k10):
    """Вхождения номера на странице: [(индекс, вид 'vid'|'tel')]."""
    return [(i, x) for i, x in enumerate(st['vh']) if x['k10'] == k10]


def main():
    db, papka, vyhod = sys.argv[1:4]
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    komp = {r['inn']: dict(r) for r in c.execute('select inn, predpriyatie, bazy, sayt from company')}
    kontakty = [dict(r) for r in c.execute('select * from contact order by inn, id')]
    tekst = zagruzit_stranicy(papka)
    out = []
    for k in kontakty:
        if k['kind'] != 'phone':
            continue
        k10, dob_db = k10_iz_value(k['value'])
        urls = [u for u in (k['source_url'] or '').replace(';', ' ').split() if u.startswith('http')]
        st = None
        otkuda = ''
        for u in urls:
            s = tekst(u)
            if s and razobrat_vhozhdeniya(s, k10):
                st, otkuda = s, 'страница'
                break
        if st is None and k['fragment']:
            s = fragment_kak_tekst(k['fragment'])
            if razobrat_vhozhdeniya(s, k10):
                st, otkuda = s, 'фрагмент'
        rec = {'id': k['id'], 'inn': k['inn'], 'value': k['value'], 'k10': k10, 'otkuda': otkuda,
               'bylo': {f: k[f] for f in ('person', 'role', 'position', 'phone_type', 'nomer_ne_lichnyy')}}
        # номер не виден на живой странице, но есть в закомментированном HTML (<!-- … -->):
        # его взяли из исходника, продавец на странице его не увидит
        zagruzheny = [tekst(u) for u in urls if tekst(u)]
        if otkuda != 'страница' and k10 and zagruzheny and any(k10 in R.cifry(x['komm']) for x in zagruzheny):
            rec['tolko_v_kommentarii'] = 1
        if st is None:
            out.append(rec)
            continue
        vh = razobrat_vhozhdeniya(st, k10)
        vidimye = [(i, x) for i, x in vh if not x['tel']]
        tolko_tel = not vidimye
        rec['tolko_tel'] = int(tolko_tel)
        varianty = []
        for i, x in (vidimye or vh):
            podp, kak = st['rm'].get(i) or R.podpis(st['t'], st['vh'], i)
            fio, dolzh = R.fio_i_dolzhnost(podp)
            varianty.append({'podp': podp[-160:], 'kak': kak, 'fio': fio, 'dolzh': dolzh,
                             'dob': x['dob'], 'okrest': st['t'][max(0, x['nach'] - 140):x['kon'] + 60]})
        rec['varianty'] = varianty
        # ссылка tel: без видимого номера рядом: что видно в тексте сразу после ссылки
        if tolko_tel:
            i, x = vh[0]
            posle = st['t'][x['kon']:x['kon'] + 60]
            m = re.match(r'\s*((?:\+\s?7|8)?[\s\-(]*\d[\d\s\-()]{8,18}\d)', posle)
            if m:
                rec['vidimyy_ryadom'] = m.group(1).strip()
        out.append(rec)
    json.dump(out, open(vyhod, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('контактов', len(out), collections.Counter(r['otkuda'] for r in out))


if __name__ == '__main__':
    main()
