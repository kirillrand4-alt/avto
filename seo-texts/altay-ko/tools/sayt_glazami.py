# -*- coding: utf-8 -*-
"""Читаю сайт ГЛАЗАМИ, а не регуляркой: печатаю сырые окна вокруг ролевых слов и почт.

Прошлый заход отвечал «людей 0» — но ноль давал ПРИБОР: он требовал, чтобы ФИО стояло в
±260 знаках от должности, а на сайтах бывает иначе (таблица «отдел — телефон — почта» без
имён, или имя в подписи новости). Здесь ничего не решается автоматом: скрипт вытаскивает
куски текста, а вывод делаю я, открыв их.

Идёт из песочницы (сервер до этих сайтов доходит хуже: 3 страницы из 16 у ПЕКО).
"""
import re
import sys
import urllib.parse
import urllib.request

TEG = re.compile(r'<(script|style)[^>]*>.*?</\1>', re.S | re.I)
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
SLOVA = re.compile(r'директор|инженер|энергетик|механик|технолог|начальник|заведующ|'
                   r'лаборатор|качеств|ОТК|снабжен|закупк|производств|главн', re.I)
POCHTA = re.compile(r'[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
TEL = re.compile(r'(?:\+7|8)[\s\-()]*\d{3,4}[\s\-()]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}'
                 r'(?:[^0-9]{0,14}(?:доб|вн)[^0-9]{0,4}\d{1,5})?', re.I)


def tekst(u):
    try:
        h = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}),
                                   timeout=35)
        kod, html = h.getcode(), h.read(2000000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:60]
    t = TEG.sub(' ', html)
    t = re.sub(r'<[^>]+>', ' | ', t)
    t = re.sub(r'&nbsp;?', ' ', t)
    t = re.sub(r'(\s*\|\s*)+', ' | ', t)
    return kod, re.sub(r'[ \t]+', ' ', t).strip(), html


BAZY = sys.argv[1:] or ['https://peko-msk.ru/']
for baza in BAZY:
    print('\n' + '=' * 78)
    print('САЙТ: %s' % baza)
    r = tekst(baza)
    if len(r) < 3 or not r[1]:
        print('  главная не открылась: код %s' % r[0])
        continue
    kod, t, html = r
    dom = urllib.parse.urlparse(baza).netloc
    ssylki = set()
    for h in re.findall(r'href=["\']([^"\'#]+)', html):
        pol = urllib.parse.urljoin(baza, h)
        if urllib.parse.urlparse(pol).netloc.endswith(dom.replace('www.', '')):
            if re.search(r'contact|kontakt|about|o-nas|o-kompanii|company|staff|team|'
                         r'rukovod|kachestv|quality|proizvod|vacan|karier|struktur|history',
                         pol, re.I):
                ssylki.add(pol.split('?')[0])
    print('  главная: код %d, знаков %d, подходящих ссылок на сайте %d'
          % (kod, len(t), len(ssylki)))
    stranicy = [baza] + sorted(ssylki)[:14]
    for u in stranicy:
        rr = tekst(u)
        if len(rr) < 3 or not rr[1]:
            print('\n  --- %s : код %s, пусто' % (u[:90], rr[0]))
            continue
        k, tt, _ = rr
        okna = []
        for m in SLOVA.finditer(tt):
            a, b = max(0, m.start() - 150), m.end() + 200
            if okna and a <= okna[-1][1]:
                okna[-1] = (okna[-1][0], b)
            else:
                okna.append((a, b))
        print('\n  --- %s : код %d, знаков %d, окон с ролевыми словами %d, почт %d, телефонов %d'
              % (u[:90], k, len(tt), len(okna), len(set(POCHTA.findall(tt))),
                 len(set(TEL.findall(tt)))))
        for a, b in okna[:12]:
            print('      … %s' % re.sub(r'\s+', ' ', tt[a:b])[:400])
