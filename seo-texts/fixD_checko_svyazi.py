# -*- coding: utf-8 -*-
"""fixD: из страниц checko (checko-meyer-html.zip, распакован в папку) достать связи юрлиц:
управляющая организация, учредители (юрлица по ОГРН, люди по ИНН, доля), руководитель-человек
(ИНН из checko-meyer-razbor.json), связанные организации из блока «Связи» (по ОГРН ссылок).

    python3 fixD_checko_svyazi.py <папка-html> <checko-meyer-razbor.json> <выход.json>
"""
import gzip
import html as H
import json
import os
import re
import sys

PAPKA, RAZBOR, VYHOD = sys.argv[1:4]
razbor = json.load(open(RAZBOR, encoding='utf-8'))


def chist(s):
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def sekciya(t, sid):
    m = re.search(r'<section id="%s".*?</section>' % sid, t, re.S)
    return m.group(0) if m else ''


def razobrat(inn):
    p = os.path.join(PAPKA, inn + '.html.gz')
    if not os.path.exists(p):
        return None
    t = gzip.open(p).read().decode('utf-8', 'replace')
    z = {'inn': inn, 'ogrn': (razbor.get(inn) or {}).get('ogrn', ''), 'naim': (razbor.get(inn) or {}).get('naim', '')}
    # управляющая организация (вместо директора-человека)
    s = sekciya(t, 'management')
    uk = []
    for m in re.finditer(r'href="/company/(?:[\w-]*?-)?(\d{13})">(.*?)</a>(.*?)(?=href="/company/|$)', s, re.S):
        inn_m = re.search(r'ИНН\s*<span[^>]*>(\d{10})<', m.group(3))
        uk.append({'ogrn': m.group(1), 'naim': chist(m.group(2)), 'inn': inn_m.group(1) if inn_m else ''})
    z['uk'] = uk
    # руководитель-человек
    r = razbor.get(inn) or {}
    z['ruk'] = {'fio': r.get('ruk_fio', ''), 'inn': r.get('ruk_inn', ''), 'vid': r.get('ruk_vid', ''),
                'dolzhnost': r.get('ruk_dolzhnost', '')}
    # учредители
    s = sekciya(t, 'founders')
    uch = []
    for tr in re.findall(r'<tr>\s*<td class="count">.*?</tr>', s, re.S):
        dolya = re.findall(r'<td class="text-nowrap[^"]*">(.*?)</td>', tr, re.S)
        dolya = chist(dolya[-1]) if dolya else ''
        mc = re.search(r'href="/company/(?:[\w-]*?-)?(\d{13})">(.*?)</a>', tr, re.S)
        mp = re.search(r'href="/person/(\d{12})">(.*?)</a>', tr, re.S)
        if mc:
            uch.append({'vid': 'org', 'id': mc.group(1), 'naim': chist(mc.group(2)), 'dolya': dolya})
        elif mp:
            uch.append({'vid': 'fl', 'id': mp.group(1), 'naim': chist(mp.group(2)), 'dolya': dolya})
        else:
            uch.append({'vid': 'inoe', 'id': '', 'naim': chist(re.sub(r'<td class="count">.*?</td>', '', tr))[:150],
                        'dolya': dolya})
    z['uchrediteli'] = uch
    # связи (первые строки списков на странице): ОГРН связанных организаций
    s = sekciya(t, 'connections')
    svyazi = []
    for m in re.finditer(r'href="/company/(?:[\w-]*?-)?(\d{13})">(.*?)</a>', s, re.S):
        svyazi.append({'ogrn': m.group(1), 'naim': chist(m.group(2))})
    z['svyazi'] = svyazi
    z['svyazi_chisla'] = re.findall(r'(По [а-яё ]+?)<span>(\d+)</span>', s)
    # основной ОКВЭД словами (первая строка «Виды деятельности»)
    s = sekciya(t, 'activity')
    m = re.search(r'<tr>\s*<td[^>]*>([\d.]+)</td>\s*<td>(.*?)</td>', s, re.S)
    z['okved_osn'] = [m.group(1), chist(m.group(2))] if m else []
    return z


vse = {}
for f in sorted(os.listdir(PAPKA)):
    if re.fullmatch(r'\d{10}\.html\.gz', f):
        z = razobrat(f[:10])
        if z:
            vse[z['inn']] = z
json.dump(vse, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print('разобрано: %d; с УК: %d; с учредителем-юрлицом: %d' % (
    len(vse), sum(1 for z in vse.values() if z['uk']), sum(1 for z in vse.values() if any(u['vid'] == 'org' for u in z['uchrediteli']))))
