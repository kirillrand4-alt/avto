# -*- coding: utf-8 -*-
"""Наш `cid` не совпадает с `company_id` строк выдачи. Проверить, что ИНН их мирит.

ОПЫТ С ФОРМАМИ ИМЕНИ ДАЛ НЕОЖИДАННЫЙ ОТВЕТ. Форма «УРАЛЬСКАЯ СТАЛЬ» вернула 25 строк,
и компания в них — «Уральская Сталь ( Металлоинвест)», то есть ровно наше предприятие.
Но СВОИХ по cid — ноль: `company_id` строки не равен `cid`, который лежит у нас в
выгрузке. Значит ломалось не имя и не фильтр, а ИДЕНТИФИКАТОР, которому я поверила.

Это уже третий за смену случай одного рода: величина, которую я считала связью, ею не
была (номер как строка, метка роли против должности, теперь cid против company_id).

ЕДИНСТВЕННЫЙ ИДЕНТИФИКАТОР, КОТОРЫЙ НЕ МОЖЕТ СОЛГАТЬ, — ИНН. Он напечатан на странице
компании площадки, и сборщик умеет его читать (режим --inn, им собран tp-inn.csv).
Прибор проверяет ровно это: взять company_id из строки выдачи, открыть страницу
компании, вычитать ИНН и сравнить с нашим. Если сходится — связь надо строить по ИНН,
а cid из выгрузки выбросить из решения (но не из файла).
"""
import json
import re
import time
import urllib.parse
import urllib.request

LIST_URL = 'https://www.tender.pro/api/tenders/list'
COMP_URL = 'https://www.tender.pro/api/company/%s/view'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
ROW = re.compile(
    r'<td[^>]*class="pr-0 tender__name"[^>]*>.*?href="/api/tender/(\d+)/view_public"[^>]*>'
    r'(.*?)</a>.*?</td>\s*<td[^>]*>([\d.]{0,10})</td>\s*<td[^>]*>([^<]{0,30})</td>'
    r'.*?href="/api/company/(\d+)/view[^"]*"[^>]*>([^<]{0,200})</a>', re.S)
INN_RE = re.compile(r'ИНН[^0-9]{0,20}(\d{10}|\d{12})')

# (наш ИНН, наш cid из выгрузки, форма имени, которая дала строки)
CELI = [('5607019523', '447142', 'УРАЛЬСКАЯ СТАЛЬ'),
        ('5103070023', '7964', 'Апатит'),
        ('6230051360', '43068', 'Завод ТЕХНО')]


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


def spisok(imya):
    q = {'sid': '', 'good_name': '', 'tender_name': '', 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': imya, 'tender_state': '100',
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0', 'company_id': '',
         'by': '25', 'order': '3', 'page': '1'}
    return ROW.findall(vzyat(LIST_URL + '?' + urllib.parse.urlencode(q)) or '')


itog = {}
for nash_inn, nash_cid, imya in CELI:
    stroki = spisok(imya)
    firmy = {}
    for _t, _p, _s, _d, cid, comp in stroki:
        firmy.setdefault(str(cid), comp.strip())
    print('\n=== «%s» | наш ИНН %s, наш cid %s | компаний в выдаче %d'
          % (imya, nash_inn, nash_cid, len(firmy)))
    sovpalo = ''
    for cid, comp in list(firmy.items())[:6]:
        h = vzyat(COMP_URL % cid)
        inn = INN_RE.search(h or '')
        inn = inn.group(1) if inn else ''
        metka = ''
        if inn == nash_inn:
            metka = '   <-- ЭТО НАШЕ ПРЕДПРИЯТИЕ'
            sovpalo = cid
        print('   company_id %-8s ИНН %-13s %s%s' % (cid, inn or '—', comp[:36], metka))
    itog[nash_inn] = {'наш cid': nash_cid, 'верный company_id': sovpalo,
                      'совпали ли': nash_cid == sovpalo}

print('\nИТОГ ' + json.dumps(itog, ensure_ascii=False))
