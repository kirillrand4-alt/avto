# -*- coding: utf-8 -*-
"""Разведка: почему тендерные агрегаторы (способ А7) дали ноль на 109 компаниях.

Ноль на выборке такого размера — это либо источник действительно пуст, либо
код молча ломается на одном из четырёх шагов. Печатаем КАЖДЫЙ шаг отдельно,
чтобы отличить одно от другого:
  1. что вообще вернул xmlriver на запрос (сколько ссылок всего);
  2. какие домены пришли в выдаче (может, агрегаторов там просто нет);
  3. что ответила страница агрегатора (байты, капча, редирект);
  4. есть ли на ней подпись «Контактное лицо» и что в окне после неё.

Запуск: python _ops_agg_probe.py [ИНН ...]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def один(inn, запрос=None):
    из = {'инн': inn, 'запрос': запрос or f'{inn} тендер контактное лицо'}
    xml = EC._xmlriver_xml(из['запрос']) if hasattr(EC, '_xmlriver_xml') else None
    if xml is None:
        # повторяем ровно ту же выборку, что делает боевой код
        import os
        import urllib.parse
        user = os.environ.get('XMLRIVER_USER', '')
        key = os.environ.get('XMLRIVER_KEY', '')
        if not (user and key):
            из['ошибка'] = 'нет XMLRIVER_USER/KEY в окружении'
            return из
        u = ('http://xmlriver.com/search_yandex/xml?user='
             + urllib.parse.quote(user) + '&key=' + urllib.parse.quote(key)
             + '&domain=ru&device=desktop&query=' + urllib.parse.quote(из['запрос']))
        try:
            xml = EC._DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace')
        except Exception as ex:  # noqa: BLE001
            из['ошибка'] = f'{type(ex).__name__}: {str(ex)[:90]}'
            return из
    из['xml_байт'] = len(xml)
    ош = re.search(r'<error[^>]*>(.{0,140})', xml, re.S)
    if ош:
        из['xml_ошибка'] = ош.group(1).strip()
    ссылки = [x.strip().replace('&amp;', '&')
              for x in re.findall(r'<url>(.*?)</url>', xml, re.S)]
    из['ссылок_всего'] = len(ссылки)
    домены = {}
    for u in ссылки:
        d = EC._domain(u)
        домены[d] = домены.get(d, 0) + 1
    из['домены'] = sorted(домены.items(), key=lambda x: -x[1])[:14]
    агг = [u for u in ссылки
           if any(EC._domain(u) == a or EC._domain(u).endswith('.' + a)
                  for a in EC._АГРЕГАТОРЫ_ТЕНДЕР)]
    из['агрегаторов_в_выдаче'] = len(агг)
    из['страницы'] = []
    for u in агг[:2]:
        стр = {'url': u[:110]}
        h, _m, mt = EC._fetch_site(u)
        стр['байт'] = len(h or '')
        стр['капча'] = mt.get('captcha_type') or ''
        стр['статус'] = mt.get('status') or mt.get('error') or ''
        if h:
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                         re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                flags=re.S | re.I)))
            стр['текст_байт'] = len(txt)
            стр['есть_инн_на_странице'] = inn in txt
            подписи = re.findall(r'Контактн\w+\s+лиц\w+\s*[:\-]?\s*(.{0,120})',
                                 txt, re.I)
            стр['подписей_контактное_лицо'] = len(подписи)
            стр['окна'] = [x[:120] for x in подписи[:3]]
            # какие ЕЩЁ подписи бывают на этих листах — вдруг формулировка иная
            for обр in ('Контакты', 'Заказчик', 'Ответственн', 'E-mail', 'Телефон'):
                стр['есть_' + обр] = обр.lower() in txt.lower()
        из['страницы'].append(стр)
    из['боевая_функция'] = EC.find_tender_aggregator_contacts(inn)
    return из


def main():
    инны = [a for a in sys.argv[1:] if a.isdigit()]
    сводка = {}
    if not инны:
        # берём ровно те компании, на которых боевой прогон дал ноль
        import io
        import os
        п = r'C:\seostat\drop\agg1.jsonl'
        ошибки = {}
        if os.path.exists(п):
            строки = [json.loads(x) for x in io.open(п, encoding='utf-8',
                                                     errors='replace') if x.strip()]
            сводка = {'строк_в_потоке': len(строки),
                      'с_ошибкой': sum(1 for x in строки if x.get('err'))}
            for x in строки:
                if x.get('err'):
                    ошибки[str(x['err'])[:70]] = ошибки.get(str(x['err'])[:70], 0) + 1
            сводка['частые_ошибки'] = sorted(ошибки.items(), key=lambda k: -k[1])[:5]
            инны = [str(x['inn']) for x in строки if not x.get('err')][:3]
    print(json.dumps({'сводка_потока': сводка,
                      'разбор': [один(i) for i in инны]},
                     ensure_ascii=False)[:7000])


if __name__ == '__main__':
    main()
