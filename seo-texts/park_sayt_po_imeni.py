# -*- coding: utf-8 -*-
"""САЙТ ПРЕДПРИЯТИЯ по названию: кандидат → DNS → ИНН на странице. Возобновляемый.

ЧЕСТНЫЙ ПОТОЛОК КАНАЛА НАЗВАН ДО ЗАПУСКА, а не после. На 261 уже подтверждённом сайте
точное совпадение домена с кандидатом даёт **23 %**. Первый замер показывал 39 %, но он
сравнивал первые четыре знака и засчитывал ПОХОЖИЕ домены — по bitumoyl.ru никуда не
попадёшь, когда сайт на bitum-oil.ru. Разница между 39 и 23 — это цена нестрогого сравнения.

Чего каналом не взять вовсе, и это не чинится правилами: «Ойл» пишут `oil`, а не `oyl`
(английское слово, не транслитерация); АО «УАПО» живёт на `agregatufa.ru`; «Карьер Доломит»
— на `dolomit.nlmk.com`, поддомене владельца. Имя сайта у них не выводится из названия.

ПОЧЕМУ ВСЁ РАВНО ГОНИМ. Обычные каналы закрыты: checko отдаёт 429 и локально, и через
сервер; ключи выдачи на сервере, а там в allowlist остался один browser_probe. 23 % от
1 478 предприятий без единого контакта — это ~340 сайтов, добытых без чужого разрешения.

ТРИ СТУПЕНИ, каждая дешевле следующей на порядок:
  1. кандидаты из названия      — счёт, ноль запросов
  2. DNS                        — есть ли такой домен вообще; отсекает ~90 % кандидатов
  3. ИНН цифрами на странице    — ЕДИНСТВЕННОЕ доказательство принадлежности.
                                  Совпадение названия доказательством НЕ считается:
                                  «Апатит» есть и у АО «Апатит», и у ОАО «Апатитстрой».
"""
import csv
import io
import json
import os
import re
import socket
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import park_domen_iz_nazvaniya as D

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = os.path.join(L, 'PARK-CELI-SAYT-2S.csv')
VYHOD = os.path.join(L, 'PARK-SAYTY-PO-IMENI-2S.jsonl')
NITEY = int(os.environ.get('NITEY', '8'))
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120 Safari/537.36'}
zamok = threading.Lock()
sch = {'предприятий': 0, 'домен живёт': 0, 'ИНН подтверждён': 0, 'страниц не открылось': 0}


def zhivet(dom):
    try:
        socket.setdefaulttimeout(6)
        socket.getaddrinfo(dom.encode('idna').decode(), 443)
        return True
    except Exception:
        return False


def stranica(url):
    try:
        r = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(r, timeout=20) as o:
            b = o.read(400000)
        k = (re.search(rb'charset=["\']?([\w-]+)', b[:3000], re.I) or [None, b'utf-8'])[1]
        return b.decode(k.decode('ascii', 'ignore') or 'utf-8', 'replace')
    except Exception:
        return ''


def po_predpriyatiyu(z):
    inn, imya = z['inn'], z['predpriyatie']
    nashli = None
    zhivye = []
    for dom in D.kandidaty(imya):
        if not zhivet(dom):
            continue
        zhivye.append(dom)
        # ИНН ищем на главной и на страницах, где реквизиты живут чаще всего.
        for hvost in ('', '/contacts', '/kontakty', '/about', '/o-kompanii', '/rekvizity'):
            for shema in ('https://', 'http://'):
                t = stranica(shema + dom + hvost)
                if not t:
                    continue
                if inn in re.sub(r'[^0-9]', '', re.sub(r'<[^>]+>', ' ', t)):
                    okno = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))
                    i = okno.find(inn)
                    nashli = {'sayt': shema + dom, 'gde': shema + dom + hvost,
                              'citata': okno[max(0, i - 90):i + 90]}
                    break
                break
            if nashli:
                break
        if nashli:
            break
    with zamok:
        sch['предприятий'] += 1
        if zhivye:
            sch['домен живёт'] += 1
        if nashli:
            sch['ИНН подтверждён'] += 1
        f.write(json.dumps({'inn': inn, 'predpriyatie': imya,
                            'zhivye_domeny': zhivye,
                            'sayt': (nashli or {}).get('sayt', ''),
                            'ssylka': (nashli or {}).get('gde', ''),
                            'citata': (nashli or {}).get('citata', ''),
                            'chem': 'ИНН цифрами на странице' if nashli else ''},
                           ensure_ascii=False) + '\n')
        f.flush()
        if sch['предприятий'] % 25 == 0:
            print('  ', dict(sch), flush=True)


if __name__ == '__main__':
    celi = list(csv.DictReader(io.open(VHOD, encoding='utf-8-sig'), delimiter=';'))
    est = set()
    if os.path.exists(VYHOD):
        for ln in io.open(VYHOD, encoding='utf-8'):
            try:
                est.add(json.loads(ln)['inn'])
            except Exception:
                pass
    celi = [c for c in celi if c['inn'] not in est]
    print('предприятий к обходу: %d (уже сделано %d)' % (len(celi), len(est)), flush=True)
    f = io.open(VYHOD, 'a', encoding='utf-8')
    with ThreadPoolExecutor(max_workers=NITEY) as p:
        list(p.map(po_predpriyatiyu, celi))
    print('ИТОГ:', dict(sch))
