# -*- coding: utf-8 -*-
"""Снять страницу «Производителям и поставщикам» сети Хлеб-соль: ФИО + должность + почта.

Найдена поиском: в сниппете видно «Зудов Андрей Владимирович. a.zudov@slata.com.
Руководитель направления Нон-фуд». Значит на странице лежит ИМЕНОВАННЫЙ список закупщиков
и категорийных менеджеров — ровно то, чего не дают ни карточка чеко, ни ЕГРЮЛ.
Из песочницы сессии домен не открывается (502 от прокси на кириллический домен),
поэтому берём с сервера.
"""
import json, re, urllib.request
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
ADRESA = ['https://xn--80abjlcbdndhcqbn6a2b.xn--p1ai/about/prices/',
          'https://xn--80abjlcbdndhcqbn6a2b.xn--p1ai/about/',
          'https://hlebsol.online/about/prices/',
          'https://slata.com/postavshchikam/', 'https://slata.com/about/']
FIO = re.compile(r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ович|евич|ьевич|овна|евна|ична))')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')
TEL = re.compile(r'\+?[78][\s(-]?\d{3,4}[\s)-]?[\s-]?\d{2,3}[\s-]?\d{2}[\s-]?\d{2}')
for u in ADRESA:
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=35).read()
    except Exception as e:
        print(json.dumps({'адрес': u, 'сбой': str(e)[:70]}, ensure_ascii=False), flush=True)
        continue
    k = (re.search(rb'charset=["\']?([\w-]+)', b[:3000], re.I) or [None, b'utf-8'])[1]
    h = b.decode(k.decode('ascii', 'ignore') or 'utf-8', 'replace')
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)))
    lyudi = []
    for m in FIO.finditer(t):
        okno = t[m.start():m.start() + 200]
        lyudi.append({'fio': m.group(1),
                      'pochta': POCHTA.findall(okno)[:1],
                      'telefon': TEL.findall(okno)[:1],
                      'posle': ' '.join(okno[len(m.group(1)):].split())[:110]})
    print(json.dumps({'адрес': u, 'знаков': len(t), 'людей': len(lyudi),
                      'спisok': lyudi[:40]}, ensure_ascii=False), flush=True)
