# -*- coding: utf-8 -*-
"""Реквизиты и руководитель четырёх предприятий из ЕГРЮЛ через dadata.

Зачем: без ИНН предприятие нельзя ни положить в базу, ни сшить с закупками, ни проверить
принадлежность найденного человека. Владелец дал ИНН только «МАЯКу» (3811125221).

Что даёт dadata кроме ИНН: `management.name` и `management.post` — это ПЕРВОЕ ЛИЦО из
ЕГРЮЛ, названное документом, а не сниппетом. Технического директора там нет никогда
(в ЕГРЮЛ его не подают), поэтому этот заход закрывает не всю задачу, а её основание.

Контроль: выдуманное предприятие. Если dadata вернёт на него карточку — прибор соглашается
с любым вводом, и все находки надо перепроверять.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')

TOKEN = os.environ.get('DADATA_TOKEN', '')
if not TOKEN:
    for put in (r'C:\sender\rs.env', r'C:\sender\server\rs.env'):
        try:
            for s in open(put, encoding='utf-8', errors='replace'):
                if s.strip().startswith('DADATA_TOKEN'):
                    TOKEN = s.split('=', 1)[1].strip().strip('"\'')
        except Exception:  # noqa: BLE001
            pass
print('токен dadata: %s (длина %d)' % ('есть' if TOKEN else 'НЕТ', len(TOKEN)))
if not TOKEN:
    sys.exit(0)

URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party'
ZAPROSY = [
    ('Брянский молочный комбинат', ['Брянский молочный комбинат', 'БМК Брянск молоко']),
    ('Хлебокомбинат ПЕКО', ['Хлебокомбинат ПЕКО', 'ПЕКО хлебокомбинат Москва']),
    ('ООО МАЯК (Хлеб-соль)', ['3811125221']),
    ('Дмитровские колбасы', ['Дмитровские колбасы', 'Дмитровский мясокомбинат колбасы']),
    ('КОНТРОЛЬ: выдуманное', ['Комбинат Щварцкопфер']),
]


def sprosit(q):
    telo = json.dumps({'query': q, 'count': 6}).encode()
    req = urllib.request.Request(URL, data=telo, headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': 'Token ' + TOKEN})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode('utf-8'))
    except Exception as e:  # noqa: BLE001
        return {'ОШИБКА': str(e)[:90]}


for imya, varianty in ZAPROSY:
    print('\n' + '=' * 78)
    print('ЦЕЛЬ: %s' % imya)
    for q in varianty:
        o = sprosit(q)
        if 'ОШИБКА' in o:
            print('  запрос «%s» — ОШИБКА: %s' % (q, o['ОШИБКА']))
            continue
        sug = o.get('suggestions') or []
        print('  запрос «%s» — карточек %d' % (q, len(sug)))
        for s in sug:
            d = s.get('data') or {}
            m = d.get('management') or {}
            print('     ИНН %-12s ОГРН %-15s %s' % (d.get('inn') or '—',
                                                    d.get('ogrn') or '—',
                                                    (s.get('value') or '')[:70]))
            print('        статус %-12s ОКВЭД %-9s %s'
                  % ((d.get('state') or {}).get('status') or '—',
                     (d.get('okved') or '—'),
                     ((d.get('address') or {}).get('value') or '')[:80]))
            if m:
                print('        РУКОВОДИТЕЛЬ: %s — %s' % (m.get('name') or '—',
                                                         m.get('post') or '—'))
            if d.get('emails'):
                print('        почты ЕГРЮЛ: %s'
                      % ', '.join((e.get('value') or '') for e in d['emails'])[:120])
            if d.get('phones'):
                print('        телефоны ЕГРЮЛ: %s'
                      % ', '.join((e.get('value') or '') for e in d['phones'])[:120])
