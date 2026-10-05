# -*- coding: utf-8 -*-
"""Люди и службы с сайтов предприятий сегментов Мейера: ФИО, должность, прямой телефон, почта.

ЗАЧЕМ. Первая сборка базы Мейера дала 372 предприятия и 2 975 строк контактов, но ролей в
них почти нет: 2 707 «не определена», ФИО всего 368 и это в основном директора из ЕГРЮЛ.
Заказчику нужны не общие телефоны, а главный инженер, технолог, качество, закупки — их на
карточке чеко нет и в ЕГРЮЛ нет, они живут только на сайте предприятия.

ДВА ВИДА НАХОДКИ, оба засчитываются:
  имя + должность      «Главный инженер Иванов Иван Иванович, тел…»
  служба без имени     «Служба технического директора: 8 (499) 473-97-30, louzgin@…»
Второй вид я чуть не потерял: заслон «признак только рядом с именем» верен для страниц, где
люди перечислены поимённо, и вреден для страниц, где перечислены СЛУЖБЫ. У ПЕКО именно так
нашлись техдиректор, лаборатория качества и снабжение.

ЧЕГО НЕ ДЕЛАЕМ. Не приписываем человеку роль, найденную где-то на той же странице: роль
страницы — не роль человека. Признак засчитывается только в ±110 знаках от имени.

Запуск: python3 park_meyer_sluzhby.py [сколько_предприятий] [нитей]
"""
import csv
import io
import json
import os
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = os.path.join(L, 'PARK-MEYER-SAYTY-2S.txt')
VYHOD = os.path.join(L, 'PARK-MEYER-LYUDI-2S.jsonl')
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 0
NITEY = int(sys.argv[2]) if len(sys.argv) > 2 else 10

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120 Safari/537.36'}
PUTI = ['', '/kontakty/', '/contacts/', '/kontakty', '/contacts', '/about/', '/o-kompanii/',
        '/rukovodstvo/', '/company/', '/struktura/', '/sotrudniki/', '/komanda/',
        '/rekvizity/', '/requisite/', '/postavshchikam/', '/suppliers/', '/zakupki/']
NUZHNO = re.compile(
    r'(главн\w+\s+инженер\w*|техническ\w+\s+директор\w*|главн\w+\s+технолог\w*|'
    r'главн\w+\s+энергетик\w*|главн\w+\s+механик\w*|директор\s+по\s+производств\w*|'
    r'директор\s+по\s+качеств\w*|начальник\w*\s+(?:отдела\s+)?качеств\w*|'
    r'специалист\w*\s+по\s+качеств\w*|производственн\w*[- ]технологическ\w*|'
    r'начальник\w*\s+лаборатори\w*|заведующ\w+\s+лаборатори\w*|\bОТК\b|'
    r'начальник\w*\s+производств\w*|заведующ\w+\s+элеватор\w*|управляющ\w+\s+элеватор\w*|'
    r'начальник\w*\s+цеха|главн\w+\s+агроном\w*|агроном\w*|семеновод\w*|'
    r'начальник\w*\s+отдела\s+закупок|отдел\w*\s+закупок|снабжен\w*|тендерн\w+\s+отдел|'
    r'коммерческ\w+\s+директор\w*|директор\s+по\s+развити\w*|'
    r'генеральн\w+\s+директор\w*|исполнительн\w+\s+директор\w*)', re.I)
FIO = re.compile(r'\b([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}'
                 r'(?:ович|евич|ьевич|овна|евна|ична|инична)'
                 r'|[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)')
TEL = re.compile(r'\+?[78][\s(\-]?\d{3,4}[\s)\-]?[\s\-]?\d{2,3}[\s\-]?\d{2}[\s\-]?\d{2}')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')
MUSOR = re.compile(r'\.(png|jpg|jpeg|svg|css|js)$|sentry|wixpress|example', re.I)

zamok = threading.Lock()
sch = {'предприятий': 0, 'сайт открылся': 0, 'с людьми': 0, 'строк': 0}


def vzyat(u):
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read()
        k = (re.search(rb'charset=["\']?([\w-]+)', b[:3000], re.I) or [None, b'utf-8'])[1]
        return b.decode(k.decode('ascii', 'ignore') or 'utf-8', 'replace')
    except Exception:
        return ''


def chisto(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).replace('&nbsp;', ' ')


def odno(z):
    inn, sayt, imya = z
    dom = re.sub(r'^https?://(www\.)?', '', sayt).rstrip('/')
    nashli, vidal, otkrylsya = [], set(), False
    for hvost in PUTI:
        h = vzyat('https://' + dom + hvost) or vzyat('https://www.' + dom + hvost)
        if not h:
            continue
        otkrylsya = True
        t = chisto(h)
        for m in NUZHNO.finditer(t):
            okno = t[max(0, m.start() - 120):m.start() + 220]
            dolzh = ' '.join(m.group(1).split())
            fio = FIO.findall(okno)
            tel = [x for x in TEL.findall(okno)]
            poch = [x for x in POCHTA.findall(okno) if not MUSOR.search(x)]
            if not (fio or tel or poch):
                continue
            k = (dolzh.lower()[:22], (fio[:1] or tel[:1] or poch[:1] or [''])[0])
            if k in vidal:
                continue
            vidal.add(k)
            nashli.append({'inn': inn, 'predpriyatie': imya, 'dolzhnost': dolzh,
                           'fio': fio[:1], 'telefony': tel[:2], 'pochty': poch[:2],
                           'ssylka': 'https://' + dom + hvost,
                           'citata': ' '.join(okno.split())[:220],
                           'vid': 'человек с должностью' if fio else 'служба без имени'})
    with zamok:
        sch['предприятий'] += 1
        if otkrylsya:
            sch['сайт открылся'] += 1
        if nashli:
            sch['с людьми'] += 1
        with io.open(VYHOD, 'a', encoding='utf-8') as f:
            for n in nashli:
                f.write(json.dumps(n, ensure_ascii=False) + '\n')
                sch['строк'] += 1
        if sch['предприятий'] % 20 == 0:
            print(json.dumps(sch, ensure_ascii=False), flush=True)


def main():
    celi = []
    for s in io.open(VHOD, encoding='utf-8'):
        ch = s.strip().split(';')
        if len(ch) >= 2 and ch[1]:
            celi.append((ch[0], ch[1], ch[2] if len(ch) > 2 else ''))
    gotovo = set()
    if os.path.exists(VYHOD):
        for s in io.open(VYHOD, encoding='utf-8'):
            try:
                gotovo.add(json.loads(s)['inn'])
            except Exception:  # noqa: BLE001
                pass
    celi = [c for c in celi if c[0] not in gotovo]
    if SKOLKO:
        celi = celi[:SKOLKO]
    print('к обходу: %d предприятий' % len(celi), flush=True)
    with ThreadPoolExecutor(max_workers=NITEY) as p:
        list(p.map(odno, celi))
    print('ИТОГ:', json.dumps(sch, ensure_ascii=False), '→', VYHOD)


if __name__ == '__main__':
    main()
