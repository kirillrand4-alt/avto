# -*- coding: utf-8 -*-
"""Почему hh «не находит работодателя»: дело в имени или в hh?

45 целей из 60 дали «не найден». Прежде чем записать это как свойство hh,
проверяю свою же строку запроса: в базе имя лежит как «ОБЩЕСТВО С
ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "РОГА"», а hh знает бренд «Рога».
"""
import csv, io, json, os, re, sys, urllib.parse, urllib.request

ДРОП = r'C:\seostat\drop\drop-storage'
УА = 'prokompressor-enrich/1.0'
_ОПФ = re.compile(
    r'^\s*(?:ПУБЛИЧНОЕ\s+|ОТКРЫТОЕ\s+|ЗАКРЫТОЕ\s+|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|'
    r'ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|МУНИЦИПАЛЬНОЕ\s+\w+|'
    r'ГОСУДАРСТВЕННОЕ\s+\w+|ФЕДЕРАЛЬНОЕ\s+\w+|УНИТАРНОЕ\s+ПРЕДПРИЯТИЕ|'
    r'ООО|ОАО|ЗАО|ПАО|АО|МУП|ГУП|ФГУП|НАО|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО)\s*', re.I)


def ядро(имя):
    s = (имя or '').strip()
    м = re.search(r'[«"]([^»"]{2,60})[»"]', s)
    if м:
        return м.group(1).strip()
    for _ in range(3):
        s = _ОПФ.sub('', s).strip()
    return re.sub(r'\s+', ' ', s).strip(' "«»')


def найти(q, tok):
    url = ('https://api.hh.ru/employers?text=' + urllib.parse.quote(q[:60])
           + '&per_page=3')
    try:
        r = urllib.request.Request(url, headers={
            'User-Agent': УА, 'Authorization': 'Bearer ' + tok})
        with urllib.request.urlopen(r, timeout=40) as о:
            d = json.loads(о.read().decode())
        it = d.get('items') or []
        return (it[0].get('name', '')[:40] if it else ''), d.get('found', 0)
    except Exception as e:  # noqa: BLE001
        return f'ОШИБКА {str(e)[:40]}', -1


def main():
    tok = os.environ.get('HH_APP_TOKEN', '')
    csv.field_size_limit(10 ** 7)
    цели = list(csv.DictReader(io.StringIO(open(
        os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv'),
        encoding='utf-8-sig', errors='replace').read()), delimiter=';'))[:14]
    было = стало = 0
    for ц in цели:
        имя = (ц.get('predpriyatie') or '').strip()
        я = ядро(имя)
        н1, f1 = найти(имя, tok)
        н2, f2 = найти(я, tok) if я and я != имя else (н1, f1)
        было += 1 if f1 else 0
        стало += 1 if f2 else 0
        print(f'  {имя[:38]:<40} → ядро «{я[:24]}»')
        print(f'      полным именем: found={f1} {н1}')
        print(f'      ядром:         found={f2} {н2}')
    print(f'\nнашлось полным именем: {было}/{len(цели)}, ядром: {стало}/{len(цели)}')


if __name__ == '__main__':
    main()
