# -*- coding: utf-8 -*-
"""ЗАМЕР Яндекс.Карт по тем же 20 компаниям.

Путь: xmlriver с additional=knowledge_graph_y — правая карточка организации
Яндекса (её источник и есть Я.Карты). Берём name/phone/address/mapurl/website.
Верификация по домену или телефону из sales_base. Ничего не пишем в базу.
"""
import json
import re
import sqlite3
import sys
import time
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'


def P(*a):
    print(*a)
    sys.stdout.flush()


def десять(p):
    d = re.sub(r'\D', '', str(p or ''))
    return d[-10:] if len(d) >= 10 else ''


_ОПФ = re.compile(
    r'\b(АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|'
    r'ПУБЛИЧНОЕ|НЕПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ|ФЕДЕРАЛЬНОЕ\s+ГОСУДАРСТВЕННОЕ|'
    r'ГОСУДАРСТВЕННОЕ\s+БЮДЖЕТНОЕ\s+УЧРЕЖДЕНИЕ|УНИТАРНОЕ\s+ПРЕДПРИЯТИЕ|'
    r'ПРЕДСТАВИТЕЛЬСТВО|ФИЛИАЛ|ООО|ОАО|ЗАО|ПАО|АО|ФГУП|ГУП|МУП|ФКП|ГБУ|АНО)\b', re.I)

_ДД = {}


def дадата(inn):
    if inn in _ДД:
        return _ДД[inn]
    tok = EC._read_secret('DADATA_TOKEN')
    из = ('', '')
    if tok and inn:
        try:
            body = json.dumps({'query': str(inn)}).encode()
            req = urllib.request.Request(
                'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                data=body, method='POST',
                headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                         'Authorization': f'Token {tok}'})
            d = json.loads(urllib.request.urlopen(req, timeout=20).read())
            s = (d.get('suggestions') or [{}])[0]
            dd = s.get('data') or {}
            ад = (dd.get('address') or {}).get('data') or {}
            из = ((ад.get('city') or ад.get('settlement') or ад.get('region') or ''),
                  ((dd.get('name') or {}).get('short_with_opf') or s.get('value') or ''))
        except Exception:  # noqa: BLE001
            из = ('', '')
    _ДД[inn] = из
    return из


def имя_для_поиска(name, ддимя):
    for сыр in (ддимя, name):
        сыр = str(сыр or '').strip()
        if not сыр:
            continue
        m = re.search(r'[«"]([^«»"]{3,60})[»"]', сыр) or re.search(r'[«"]([^«»"]{3,60})$', сыр)
        if m:
            return m.group(1).strip()
        чист = re.sub(r'\s+', ' ', _ОПФ.sub(' ', сыр)).strip().strip('"«»')
        if чист:
            return чист
    return ''


def кг(q):
    """Сырой XML выдачи + разобранная карточка знаний."""
    user = EC._read_secret('XMLRIVER_USER') or ''
    key = EC._read_secret('XMLRIVER_KEY') or ''
    if not (user and key):
        return {}, '', 'нет ключей xmlriver'
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&additional=knowledge_graph_y&query=' + urllib.parse.quote(q))
    for att in range(3):
        try:
            raw = EC._DIRECT.open(url, timeout=35).read()
            xml = EC._раскодировать(raw, 'charset=utf-8')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                time.sleep(2 * (att + 1))
                continue
            return EC._parse_kg(xml), xml, ''
        except Exception as ex:  # noqa: BLE001
            time.sleep(2 * (att + 1))
            посл = f'{type(ex).__name__}'
    return {}, '', 'xmlriver не ответил'


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    d = json.load(open(БАЗА, encoding='utf-8'))
    строки = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                строки += v
    else:
        строки = d
    по_инн = {}
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in по_инн:
            по_инн[i] = x
    con = sqlite3.connect(EDB.DB_PATH)
    cur = con.cursor()
    пул = []
    for inn, x in по_инн.items():
        r = cur.execute('SELECT name, site, region FROM companies WHERE inn=?',
                        (inn,)).fetchone()
        if not r or not (r[1] or ''):
            continue
        пул.append({'inn': inn, 'name': r[0] or str(x.get('name') or ''),
                    'site': r[1], 'region': r[2] or '',
                    'phones': [десять(p) for p in (x.get('phones') or [])]})
        if len(пул) >= n:
            break

    ст = {'компаний': len(пул), 'карточка': 0, 'подтверждена': 0, 'с_телефоном': 0,
          'тел_всего': 0, 'с_mapurl': 0, 'с_email': 0, 'нет_карточки': 0}
    строки_вывода = []
    for c in пул:
        город, ддимя = дадата(c['inn'])
        город = re.sub(r'^(г|город|пгт|с|село|рп)\.?\s+', '', город or '', flags=re.I)
        имя = имя_для_поиска(c['name'], ддимя)
        q = f'{имя} {город}'.strip()
        card, xml, err = кг(q)
        if not card:
            ст['нет_карточки'] += 1
            P(f'  [-] {c["inn"]} {имя[:26]!r} ({город[:14]}) — карточки нет '
              f'{err[:40]} xml={len(xml)}')
            continue
        ст['карточка'] += 1
        тел = [t for t in re.split(r'[;,]\s*', str(card.get('phone') or '')) if t.strip()]
        ст['тел_всего'] += len(тел)
        if тел:
            ст['с_телефоном'] += 1
        if card.get('mapurl'):
            ст['с_mapurl'] += 1
        if card.get('email'):
            ст['с_email'] += 1
        наш = EC._domain('http://' + re.sub(r'^https?://', '', c['site']))
        кгдом = EC._domain(str(card.get('website') or ''))
        тел10 = {десять(t) for t in тел}
        ок = (наш and кгдом and наш == кгдом) or bool(тел10 & set(c['phones']))
        if ок:
            ст['подтверждена'] += 1
        P(f'  [+] {c["inn"]} {имя[:24]!r} подтв={bool(ок)} тел={тел} '
          f'сайт={кгдом} тип={str(card.get("type"))[:18]} mapurl={bool(card.get("mapurl"))}')
        if len(строки_вывода) < 4:
            строки_вывода.append((имя, card))

    P('')
    for имя, card in строки_вывода:
        P('  СЫРАЯ КАРТОЧКА', имя[:24], ':', json.dumps(card, ensure_ascii=False)[:420])
    P('ИТОГ ЯКАРТЫ: ' + json.dumps(ст, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))
