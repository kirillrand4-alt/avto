# -*- coding: utf-8 -*-
"""Почему страница компании не открылась: код ответа, а не слово «не открылась».

36 компаний подряд дали «страница не открылась», хотя минутой раньше те же самые
страницы у company_id 7571 и 46105 открылись и отдали ИНН. Значит дело не в площадке
вообще, а в чём-то различающем эти случаи, — и узнать это можно только по коду
ответа, который мой сборщик выбросил, оставив общее слово.

Это тот же промах, что и «__ОШИБКА__» без причины: прибор сообщает, ЧТО не вышло, и
молчит о том, ПОЧЕМУ. Разница между 403, 404 и таймаутом — это разница между
«закрыто для нас», «такой компании нет» и «мы слишком частим», и лечится она
по-разному.

Заодно проверяю догадку про частоту: те два запроса шли по одному, эти 36 — в четыре
потока. Поэтому здесь строго последовательно и с паузой.
"""
import json
import re
import time
import urllib.error
import urllib.request

COMP_URL = 'https://www.tender.pro/api/company/%s/view'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
INN_RE = re.compile(r'ИНН[^0-9]{0,20}(\d{10}|\d{12})')

# Первые два открывались час назад — контроль. Остальные из числа «не открылись».
CELI = [('7571', 'контроль: открывался'), ('46105', 'контроль: открывался'),
        ('207951', 'Уральская Сталь ( Металлоинвест)'), ('74727', 'ФосАгро-Череповец'),
        ('7565', 'Аммофос'), ('29568', 'Руссдрагмет')]

itog = {}
for cid, podpis in CELI:
    otvet = ''
    for popytka in (1, 2):
        try:
            rq = urllib.request.Request(COMP_URL % cid,
                                        headers={'User-Agent': UA,
                                                 'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(rq, timeout=60) as r:
                h = r.read().decode('utf-8', 'replace')
            m = INN_RE.search(h)
            otvet = 'код %s, знаков %d, ИНН %s' % (r.status, len(h),
                                                   m.group(1) if m else 'в тексте нет')
            break
        except urllib.error.HTTPError as e:
            otvet = 'HTTP %s %s' % (e.code, e.reason)
        except Exception as e:  # noqa: BLE001
            otvet = '%s: %s' % (type(e).__name__, str(e)[:70])
        time.sleep(3)
    print('  %-8s %-34s %s' % (cid, podpis[:34], otvet))
    itog[cid] = otvet
    time.sleep(2.0)

print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
