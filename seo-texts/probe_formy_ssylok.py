# -*- coding: utf-8 -*-
"""Какие формы ссылок уже есть у контактов — чтобы восстанавливать по образцу, а не по догадке.

ПОЧЕМУ НЕЛЬЗЯ ПРОСТО ПОДСТАВИТЬ ССЫЛКУ ФАКТА. У предприятия есть факты со ссылками на закупки,
но контакт пришёл НЕ ОТТУДА. Приписать контакту адрес чужой карточки — это выдумать провенанс,
а выдуманный источник хуже пустого: пустой честно говорит «не знаем», выдуманный отправляет
человека проверять не туда и выглядит доказательством.

Поэтому смотрю, какие адреса УЖЕ стоят у контактов каждого источника: если у 105 контактов
`tender.pro` ссылка есть, её форма и есть канон для тех 75, у кого её нет.
"""
import collections
import json
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
o = {}
formy = collections.defaultdict(collections.Counter)
for src, url in cx.execute(
        "select coalesce(source,''), coalesce(source_url,'') from person "
        "where coalesce(source_url,'') <> ''"):
    # Форма адреса: домен плюс скелет пути с цифрами, заменёнными на N.
    m = re.match(r'https?://([^/]+)(/[^?#]*)?', url)
    if not m:
        continue
    put = re.sub(r'\d+', 'N', m.group(2) or '/')
    formy[src.split(';')[0].strip()[:40]][f'{m.group(1)}{put[:60]}'] += 1
o['формы_по_источникам'] = {k: v.most_common(3) for k, v in
                            sorted(formy.items(), key=lambda x: -sum(x[1].values()))[:10]}
o['примеры_tender_pro'] = cx.execute(
    "select coalesce(source,''), coalesce(source_url,'') from person "
    "where lower(coalesce(source,'')) like '%tender%' and coalesce(source_url,'') <> '' "
    "limit 5").fetchall()
o['примеры_egrul'] = cx.execute(
    "select coalesce(source,''), coalesce(source_url,'') from person "
    "where lower(coalesce(source,'')) like '%егрюл%' or lower(coalesce(source,'')) like '%dadata%' "
    "limit 5").fetchall()
# У фактов какие формы для тех же площадок — вдруг канон виден там.
o['формы_фактов_tender'] = cx.execute(
    "select coalesce(source_url,''), count(*) from fact "
    "where lower(coalesce(source_url,'')) like '%tender.pro%' group by 1 limit 4").fetchall()
print(json.dumps(o, ensure_ascii=False, indent=1)[:3500])
