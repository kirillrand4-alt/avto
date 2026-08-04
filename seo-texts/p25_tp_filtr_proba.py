# -*- coding: utf-8 -*-
"""Какой параметр формы площадки ДЕЙСТВИТЕЛЬНО сужает выдачу до одного предприятия.

ЗАЧЕМ ОТДЕЛЬНЫЙ ПРИБОР. Прогон по компаниям вернул «тендеров 2820» у ВСЕХ восьми
предприятий подряд — одно и то же число у РТ-Инжиниринга, Апатита и Карабашмеди.
Одинаковое большое число у разных входов означает, что фильтр не применён и выдача
общая. Моя проба перед прогоном спрашивала «жив ли фильтр» так: пришли ли ссылки на
тендеры. Пришли — значит жив. Это не проверка: непустая выдача бывает и без фильтра.

Правильная проверка фильтра описана в моём же сборщике и называется контрольной
бессмыслицей: осмысленное значение и заведомо несуществующее должны дать РАЗНОЕ.
Плюс два разных предприятия должны дать разное между собой. Три условия:

    A) значение №1 и значение №2  ->  разные наборы номеров тендеров
    B) заведомо битое значение    ->  пусто или заметно меньше
    C) без параметра вовсе        ->  больше, чем с ним

Проверяю несколько имён параметра сразу, потому что какое из них рабочее — вопрос к
источнику, а не ко мне.
"""
import json
import re
import time
import urllib.parse
import urllib.request

LIST_URL = 'https://www.tender.pro/api/tenders/list'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
ID_TENDER = re.compile(r'/api/tender/(\d+)/view')

# Две живые компании площадки с разными закупками и заведомая бессмыслица.
CID_1, CID_2, CID_BRED = '371656', '2831', '99999999'
IMENA_1, IMENA_2 = 'РТ-Инжиниринг', 'Апатит'


def vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            rq = urllib.request.Request(url, headers={'User-Agent': UA,
                                                      'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return '__ОШИБКА__ %s' % type(e).__name__
            time.sleep(1.5 * (p + 1))


def url_s(dop):
    q = {'sid': '', 'good_name': '', 'tender_name': '', 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': '', 'tender_state': '100',
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0', 'company_id': '',
         'by': '25', 'order': '3', 'page': '1'}
    q.update(dop)
    return LIST_URL + '?' + urllib.parse.urlencode(q)


def nabor(dop):
    h = vzyat(url_s(dop))
    if not h or h.startswith('__ОШИБКА__'):
        return None, h
    return set(ID_TENDER.findall(h)), ''


bez, _ = nabor({})
print('БЕЗ ФИЛЬТРА: номеров на первой странице %s' % (len(bez) if bez is not None else '—'))

for imya in ('company_id', 'sid', 'company_name', 'tender_promoter_id', 'promoter_id',
             'organizator_id', 'customer_id'):
    a, _ = nabor({imya: CID_1})
    b, _ = nabor({imya: CID_2})
    c, _ = nabor({imya: CID_BRED})
    if a is None or b is None or c is None:
        print('  %-20s запрос не прошёл' % imya)
        continue
    razlichaet = (a != b)
    bred_pust = (len(c) == 0 or c != a)
    suzhaet = (bez is not None and (a != bez or len(a) < len(bez)))
    print('  %-20s №1=%2d №2=%2d бред=%2d | различает %-5s | бред отличается %-5s | '
          'сужает %-5s%s'
          % (imya, len(a), len(b), len(c), razlichaet, bred_pust, suzhaet,
             '   <-- РАБОЧИЙ' if (razlichaet and bred_pust and suzhaet) else ''))

# Отдельно текстом: имя компании как строка часто работает там, где id не работает.
for imya in ('company_name', 'tender_name'):
    a, _ = nabor({imya: IMENA_1})
    b, _ = nabor({imya: IMENA_2})
    c, _ = nabor({imya: 'кастрюлякастрюля'})
    if a is None or b is None or c is None:
        continue
    print('  %-20s(текст) №1=%2d №2=%2d бессмыслица=%2d | различает %s'
          % (imya, len(a), len(b), len(c), a != b))

print('ИТОГ ' + json.dumps({'без фильтра на странице': len(bez) if bez else 0},
                           ensure_ascii=False))
