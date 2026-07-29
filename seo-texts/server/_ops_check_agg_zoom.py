# -*- coding: utf-8 -*-
"""Зум в те листы агрегаторов, где сырьё показало живой контакт ЗАКАЗЧИКА.

Первый заход дал улику: на листе tenderguru лежит zakupki@lorp.ru и телефон
+7(4112)408009 — это почта заказчика, а не агрегатора, при этом боевая
регулярка «Контактное лицо» не нашла НИ ОДНОГО окна. Значит вопрос не «пусто
ли», а «как подписано». Печатаем широкое сырьё вокруг каждой почты и каждого
телефона и вокруг слов-подписей — без интерпретаций.

Плюс проверяем массовость: у ещё двух ИНН ищем лист tenderguru/tender и
смотрим, есть ли и там почта заказчика.
"""
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ЛИСТЫ = [
    'https://www.tenderguru.ru/tender/64392184',
    'https://www.bicotender.ru/company29082.html',
]


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def зум(u, P, глубоко=True):
    h, метод, mt = EC._fetch_site(u)
    if not h:
        P(f'  {u[:80]} ПУСТО {mt}')
        return 0
    t = текст(h)
    P(f'  ЛИСТ {u[:90]} текст={len(t)} метод={метод}')
    почты = sorted(set(x.lower() for x in EC.EMAIL_RE.findall(t)))
    чужие = [e for e in почты
             if not any(a.split('.')[0] in e for a in EC._АГРЕГАТОРЫ_ТЕНДЕР)
             and 'tender' not in e and 'datahub' not in e]
    P(f'    почты_НЕ_агрегатора={чужие}')
    if not глубоко:
        return len(чужие)
    for e in чужие[:3]:
        i = t.lower().find(e)
        if i >= 0:
            P('    вокруг_почты> ' + t[max(0, i - 420):i + 220])
    # телефоны с контекстом
    n = 0
    for m in EC.phones_in(t):
        s = m.group(0).strip()
        if '800' in s.replace(' ', '').replace('-', '')[:4]:
            continue   # горячая линия агрегатора
        P('    вокруг_телефона> ' + t[max(0, m.start() - 300):m.start() + 160])
        n += 1
        if n >= 2:
            break
    # что стоит рядом со словами-подписями, которых боевой код не знает
    for сл in ('Менеджер', 'Ответственн', 'Куратор', 'Контактн', 'Организатор',
               'Заказчик'):
        for i, m in enumerate(re.finditer(сл, t, re.I)):
            if i >= 1:
                break
            P(f'    подпись[{сл}]> ' + t[m.start():m.start() + 300])
    return len(чужие)


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    итог = {'листов': 0, 'с_почтой_заказчика': 0, 'массово_проверено': 0,
            'массово_с_почтой': 0}
    P('=== ЗУМ В ИЗВЕСТНЫЕ ЛИСТЫ ===')
    for u in ЛИСТЫ:
        итог['листов'] += 1
        if зум(u, P):
            итог['с_почтой_заказчика'] += 1

    # массовость: ещё несколько ИНН -> лист tenderguru/tender
    P('=== МАССОВОСТЬ: другие ИНН ===')
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    инны = [a for a in sys.argv[1:] if a.isdigit()]
    if not инны:
        п = r'C:\sender\_ops\sales_base.json'
        if os.path.exists(п):
            d = json.load(open(п, encoding='utf-8', errors='replace'))
            строки = d if isinstance(d, list) else (d.get('rows') or d.get('items') or [])
            for x in строки:
                s = str((x or {}).get('inn') or '')
                if s.isdigit() and s not in инны:
                    инны.append(s)
    P(f'  ИНН в базе продажников: {len(инны)}')
    for inn in инны[:3]:
        q = f'{inn} tenderguru тендер'
        u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
             + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
             + '&query=' + urllib.parse.quote(q))
        try:
            xml = EC._DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace')
        except Exception as ex:  # noqa: BLE001
            P(f'  {inn}: выдача не пришла {type(ex).__name__}')
            continue
        цели = [x.strip().replace('&amp;', '&')
                for x in re.findall(r'<url>(.*?)</url>', xml, re.S)
                if '/tender/' in x or 'zakupki_organizaciy' in x]
        P(f'  ИНН {inn}: листов tenderguru в выдаче={len(цели)}')
        for c in цели[:1]:
            итог['массово_проверено'] += 1
            if зум(c, P, глубоко=False):
                итог['массово_с_почтой'] += 1
    print('\n'.join(буф)[-11000:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
