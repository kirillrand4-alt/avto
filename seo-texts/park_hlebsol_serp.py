# -*- coding: utf-8 -*-
"""Люди сети «Хлеб-соль»/«Слата» из СНИППЕТОВ выдачи: страница поставщикам недостижима напрямую.

Домен кириллический, сервер его не резолвит (getaddrinfo failed), из песочницы прокси даёт
502. Но поисковая выдача уже показала, что на странице лежит именованный список:
«Зудов Андрей Владимирович. a.zudov@slata.com. Руководитель направления Нон-фуд».
Берём то, что отдаёт выдача, — со ссылкой на страницу, откуда снято.
"""
import json, os, re, urllib.parse, urllib.request
USER = os.environ.get('XMLRIVER_USER', '')
KEY = os.environ.get('XMLRIVER_KEY', '')
ZAPROSY = [
    'хлебсольдискаунт производителям и поставщикам категорийный менеджер',
    'slata.com категорийный менеджер @slata.com',
    '"@slata.com" категорийный менеджер Слата',
    '"@slata.com" руководитель направления',
    'Слата Иркутск отдел закупок категорийный менеджер контакты почта',
    'хлебсольдискаунт.рф поставщикам контакты менеджер',
]
FIO = re.compile(r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ович|евич|ьевич|овна|евна|ична))')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')


def serp(q):
    u = ('http://xmlriver.com/search/xml?user=%s&key=%s&query=%s&groupby=30'
         % (USER, KEY, urllib.parse.quote(q)))
    try:
        x = urllib.request.urlopen(u, timeout=45).read().decode('utf-8', 'replace')
    except Exception as e:
        return [{'err': str(e)[:70]}]
    out = []
    for m in re.finditer(r'<doc>(.*?)</doc>', x, re.S):
        d = m.group(1)
        url = (re.search(r'<url>(.*?)</url>', d, re.S) or [None, ''])[1]
        tit = re.sub(r'<[^>]+>', ' ', (re.search(r'<title>(.*?)</title>', d, re.S) or [None, ''])[1])
        pas = re.sub(r'<[^>]+>', ' ', (re.search(r'<passages>(.*?)</passages>', d, re.S) or [None, ''])[1])
        out.append({'url': url, 't': ' '.join((tit + ' ' + pas).split())})
    return out


lyudi = {}
for q in ZAPROSY:
    for d in serp(q):
        if d.get('err'):
            print(json.dumps({'ошибка': d['err']}, ensure_ascii=False), flush=True)
            break
        t = d['t']
        for m in FIO.finditer(t):
            okno = t[m.start():m.start() + 190]
            poch = POCHTA.findall(okno)
            # Должность — то, что идёт ПОСЛЕ почты: так устроена сама страница
            posle = okno
            if poch:
                i = okno.find(poch[0]) + len(poch[0])
                posle = okno[i:]
            lyudi[m.group(1)] = {'fio': m.group(1), 'pochta': poch[:1],
                                 'dolzhnost': ' '.join(posle.split())[:80],
                                 'ssylka': d['url'], 'zapros': q}
print(json.dumps({'найдено людей': len(lyudi), 'люди': list(lyudi.values())[:40]},
                 ensure_ascii=False), flush=True)
