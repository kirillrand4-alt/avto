# -*- coding: utf-8 -*-
"""Поиск ИМЕНОВАННЫХ технических ЛПР по четырём целям владельца — через xmlriver с боевого.

Роли по заданию: главный инженер, технический директор, директор/специалист по качеству,
главный технолог, начальник производства; снабжение — во вторую очередь.
Отдельно: «Феликс Николаевич», технический директор Дмитровских колбас (назван владельцем).

ЧТО СЧИТАЕТСЯ НАХОДКОЙ. Только ФИО, стоящее РЯДОМ с должностью в тексте сниппета
(±140 знаков), со ссылкой на страницу. Роль со страницы — это роль страницы, а не человека:
на этом я уже обжёгся, когда коммерческий директор получил роль «наша» по чужому инженеру.
"""
import json, os, re, sys, urllib.parse, urllib.request

USER = os.environ.get('XMLRIVER_USER', '')
KEY = os.environ.get('XMLRIVER_KEY', '')
CELI = [
    ('Дмитровские колбасы', ['"Дмитровские колбасы" "Феликс Николаевич"',
                             '"Дмитровские колбасы" технический директор',
                             '"Дмитровские колбасы" главный инженер']),
    ('Брянский молочный комбинат', ['"Брянский молочный комбинат" главный инженер',
                                    '"Брянский молочный комбинат" технический директор',
                                    '"Брянский молочный комбинат" директор по качеству']),
    ('Хлебокомбинат ПЕКО', ['"Хлебокомбинат ПЕКО" главный инженер',
                            '"ПЕКО" хлебокомбинат технический директор',
                            '"Хлебокомбинат ПЕКО" начальник лаборатории качество']),
    ('МАЯК Хлеб-соль', ['"Хлеб-соль" Слата главный инженер',
                        '"Слата" технический директор Иркутск',
                        '"Хлеб-соль" директор по качеству']),
]
DOLZH = re.compile(r'(главн\w+\s+инженер|техническ\w+\s+директор|директор\s+по\s+качеств|'
                   r'начальник\w*\s+(?:отдела\s+)?(?:контрол\w+\s+)?качеств|главн\w+\s+технолог|'
                   r'главн\w+\s+энергетик|главн\w+\s+механик|начальник\w*\s+производств|'
                   r'начальник\w*\s+лаборатори|директор\s+по\s+производств)', re.I)
FIO = re.compile(r'[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]{2,})?')


def serp(q):
    if not (USER and KEY):
        return []
    u = ('http://xmlriver.com/search/xml?user=%s&key=%s&query=%s&groupby=30'
         % (USER, KEY, urllib.parse.quote(q)))
    try:
        x = urllib.request.urlopen(u, timeout=45).read().decode('utf-8', 'replace')
    except Exception as e:
        return [{'err': str(e)[:90]}]
    out = []
    for m in re.finditer(r'<doc>(.*?)</doc>', x, re.S):
        d = m.group(1)
        url = (re.search(r'<url>(.*?)</url>', d, re.S) or [None, ''])[1]
        tit = re.sub(r'<[^>]+>', ' ', (re.search(r'<title>(.*?)</title>', d, re.S) or [None, ''])[1])
        pas = re.sub(r'<[^>]+>', ' ', (re.search(r'<passages>(.*?)</passages>', d, re.S) or [None, ''])[1])
        out.append({'url': url, 'tekst': ' '.join((tit + ' ' + pas).split())})
    return out


for imya, zaprosy in CELI:
    nashli, vidal = [], set()
    for q in zaprosy:
        for d in serp(q):
            if d.get('err'):
                print(json.dumps({'цель': imya, 'ошибка': d['err']}, ensure_ascii=False), flush=True)
                continue
            t = d['tekst']
            for m in DOLZH.finditer(t):
                okno = t[max(0, m.start() - 140):m.start() + 160]
                for f in FIO.findall(okno):
                    if f.split()[0].lower() in ('главный', 'технический', 'директор', 'начальник'):
                        continue
                    k = (f, m.group(1).lower()[:16])
                    if k in vidal:
                        continue
                    vidal.add(k)
                    nashli.append({'fio': f, 'dolzhnost': m.group(1), 'zapros': q,
                                   'ssylka': d['url'], 'citata': okno[:200]})
    print(json.dumps({'цель': imya, 'найдено': len(nashli), 'люди': nashli[:12]},
                     ensure_ascii=False), flush=True)
