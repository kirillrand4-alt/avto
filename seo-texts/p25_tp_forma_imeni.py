# -*- coding: utf-8 -*-
"""Какой ФОРМОЙ имени площадка находит предприятие. Опыт, а не догадка.

39 предприятий из 45 дали пустую выдачу по имени, и это не «их там нет»: «Апатит»
одним словом нашёл 1 020 строк, а «Карабашмедь» одним словом — ноль. Значит дело в
форме написания, и её надо установить опытом, а не рассуждением.

Проверяю пять форм на одном и том же предприятии:

    1) как лежит у нас                 «АО УРАЛЬСКАЯ СТАЛЬ (Новотроицк)»
    2) без города                      «АО УРАЛЬСКАЯ СТАЛЬ»
    3) без правовой формы              «УРАЛЬСКАЯ СТАЛЬ»
    4) одно самое длинное слово        «УРАЛЬСКАЯ»
    5) полное юридическое из p25.db    «АО "УРАЛЬСКАЯ СТАЛЬ"»

Строк меряю ДВЕ величины: сколько вернулось всего и сколько из них с нашим cid.
Форма, дающая строки, но ни одной своей, ничем не лучше пустой — она лишь выглядит
удачной, а это ровно та ошибка, за которую я сегодня заплатила 2 399 карточками.
"""
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request

LIST_URL = 'https://www.tender.pro/api/tenders/list'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
ID_TENDER = re.compile(r'/api/tender/(\d+)/view')
ROW = re.compile(
    r'<td[^>]*class="pr-0 tender__name"[^>]*>.*?href="/api/tender/(\d+)/view_public"[^>]*>'
    r'(.*?)</a>.*?</td>\s*<td[^>]*>([\d.]{0,10})</td>\s*<td[^>]*>([^<]{0,30})</td>'
    r'.*?href="/api/company/(\d+)/view[^"]*"[^>]*>([^<]{0,200})</a>', re.S)
GOROD = re.compile(r'\s*\([^)]*\)\s*$')
FORMA = re.compile(r'^(?:ООО|ОАО|ЗАО|АО|ПАО|НАО|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|ПУБЛИЧНОЕ\s+'
                   r'АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+'
                   r'ОТВЕТСТВЕННОСТЬЮ)\s*', re.I)

CELI = [('2623026057', '303556', 'Компрессор-Техцентр (Ставрополь)'),
        ('5607019523', '447142', 'АО УРАЛЬСКАЯ СТАЛЬ (Новотроицк)'),
        ('7406002523', '60486', 'Карабашмедь'),
        ('5103070023', '7964', 'Апатит (Кировск)'),
        ('4028001072', '261805', 'КАЛУГАГЛАВСНАБ (Калуга)')]


def vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            rq = urllib.request.Request(url, headers={'User-Agent': UA,
                                                      'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            if p == popytok - 1:
                return ''
            time.sleep(1.5 * (p + 1))


def sprosit(imya, cid):
    q = {'sid': '', 'good_name': '', 'tender_name': '', 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': imya, 'tender_state': '100',
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0', 'company_id': '',
         'by': '25', 'order': '3', 'page': '1'}
    h = vzyat(LIST_URL + '?' + urllib.parse.urlencode(q))
    stroki = ROW.findall(h or '')
    svoih = sum(1 for r in stroki if str(r[4]) == str(cid))
    firmy = {r[5].strip()[:40] for r in stroki}
    return len(set(ID_TENDER.findall(h or ''))), svoih, sorted(firmy)[:3]


b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
yur = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}

luchshie = {}
for inn, cid, tp_name in CELI:
    polnoe = yur.get(inn, '')
    bez_goroda = GOROD.sub('', tp_name)
    bez_formy = FORMA.sub('', bez_goroda).strip(' "«»')
    odno = max(bez_formy.replace('-', ' ').split() or [''], key=len)
    yadro = FORMA.sub('', polnoe).strip(' "«»')
    formy = [('как у нас', tp_name), ('без города', bez_goroda),
             ('без правовой формы', bez_formy), ('одно слово', odno),
             ('ядро юр. имени', yadro)]
    print('\n=== %s | ИНН %s | cid %s' % (tp_name[:44], inn, cid))
    for nazvanie, v in formy:
        if not v:
            continue
        vsego, svoih, firmy = sprosit(v, cid)
        print('   %-20s «%-34s» строк %2d, СВОИХ %2d %s'
              % (nazvanie, v[:34], vsego, svoih, firmy if vsego and not svoih else ''))
        if svoih and inn not in luchshie:
            luchshie[inn] = (nazvanie, v, svoih)

print('\nИТОГ ' + json.dumps({
    'предприятий в опыте': len(CELI), 'нашлись своей формой': len(luchshie),
    'формы': {k: v[0] for k, v in luchshie.items()}}, ensure_ascii=False))
