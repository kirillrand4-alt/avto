# -*- coding: utf-8 -*-
"""Веер запросов, заход ТРЕТИЙ-БИС: печать компактная, потому что прошлый вывод СРЕЗАЛО.

Урок прошлого прогона, названный прямо: сервер отдаёт только хвост stdout, и 37 подробных
блоков в него не влезли — я увидела два последних запроса из тридцати семи. Ноль информации
по четырём целям выглядел как «прогон не дал ничего», хотя прогон отработал полностью.
Поэтому здесь: одна строка на запрос, и подробности ТОЛЬКО у тех документов, где в сниппете
есть и ролевое слово, и похожее на ФИО.

Второй урок — про контроль. Выдуманная фамилия при живом предприятии дала 14 документов,
столько же, сколько настоящий запрос: Яндекс отвечает всегда. Значит «документы нашлись» не
значит ничего, и различать надо не по числу документов, а по тому, стоят ли в сниппете
ИСКОМЫЕ слова. Ниже так и считается: `sovpalo` — сколько документов реально содержат
и имя предприятия, и ролевое слово.
"""
import os
import re
import time
import urllib.parse
import urllib.request

USER = os.environ.get('XMLRIVER_USER', '')
KEY = os.environ.get('XMLRIVER_KEY', '')
TEG = re.compile(r'<[^>]+>')
FIO = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:вич|вна|ична)|'
                 r'[А-ЯЁ][а-яё]{2,}(?:вич|вна|ична)\s+[А-ЯЁ][а-яё\-]{3,}|'
                 r'[А-ЯЁ][а-яё\-]{3,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.')
ROL = re.compile(r'техническ\w+\s+директор|техдиректор|главн\w+\s+(?:инженер|энергетик|механик|'
                 r'технолог)|начальник\w*\s+(?:цеха|производства|лаборатории|отдела|службы)|'
                 r'директор\s+по\s+(?:качеству|производству|развитию)|заведующ\w+\s+производством',
                 re.I)


def snyat(tag, kus):
    m = re.search(r'<%s>(.*?)</%s>' % (tag, tag), kus, re.S)
    return re.sub(r'\s+', ' ', TEG.sub(' ', m.group(1))).strip() if m else ''


def vydacha(q, n=10):
    if not (USER and KEY):
        return [], 'нет ключей'
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(USER)
           + '&key=' + urllib.parse.quote(KEY) + '&domain=ru&device=desktop&groupby=' + str(n)
           + '&query=' + urllib.parse.quote(q))
    xml = ''
    for att in range(4):
        try:
            xml = urllib.request.urlopen(url, timeout=45).read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            time.sleep(4 + att * 4)
            continue
        if 'свободных каналов' in xml or 'no free channel' in xml.lower():
            time.sleep(6 + att * 5)
            xml = ''
            continue
        break
    if not xml:
        return [], 'ОТКАЗ'
    docs = []
    for kus in re.findall(r'<doc>(.*?)</doc>', xml, re.S):
        docs.append((snyat('url', kus), snyat('title', kus),
                     ' '.join(re.sub(r'\s+', ' ', TEG.sub(' ', x)).strip()
                              for x in re.findall(r'<passage>(.*?)</passage>', kus, re.S))))
    return docs, ('пусто' if not docs else 'ок')


CELI = [
    ('БМК', '"Брянский молочный комбинат"', ('брянск', 'бмк')),
    ('ПЕКО', '"Хлебокомбинат ПЕКО"', ('пеко',)),
    ('МАЯК/Хлеб-соль', '"Хлеб-Соль" Иркутск', ('хлеб-соль', 'маяк', 'иркутск')),
    ('ДмитрКолбасы', '"Дмитровские колбасы"', ('дмитровск',)),
    ('КОНТРОЛЬ', '"Комбинат Щварцкопфер"', ('щварцкопфер',)),
]
ROLI = ['"главный инженер"', '"главный энергетик"', '"технический директор"',
        '"главный механик"', '"главный технолог"', '"директор по качеству"',
        '"начальник производства"', '"начальник цеха"']

itog = {}
for imya, baza, kuski in CELI:
    print('\n===== %s' % imya)
    vsego_sovp = 0
    for rol in ROLI:
        docs, sost = vydacha(baza + ' ' + rol, 10)
        nashli = []
        sovpalo = 0
        for u, t, p in docs:
            s = t + ' ' + p
            niz = s.lower()
            svoy = any(k in niz for k in kuski)
            if svoy and ROL.search(s):
                sovpalo += 1
                if FIO.search(s):
                    nashli.append((FIO.search(s).group(0), u, s))
        vsego_sovp += sovpalo
        print('  %-24s док %2d · с именем предприятия И ролью %d · С ФИО %d · %s'
              % (rol.strip('"')[:24], len(docs), sovpalo, len(nashli), sost))
        for f, u, s in nashli[:3]:
            print('      ★ %s' % f)
            print('        %s' % u[:105])
            print('        S: %s' % re.sub(r'\s+', ' ', s)[:260])
        time.sleep(1)
    itog[imya] = vsego_sovp

print('\n########## ИТОГ: документов, где стоят И предприятие, И ролевое слово')
for k, v in itog.items():
    print('  %-16s %d' % (k, v))
