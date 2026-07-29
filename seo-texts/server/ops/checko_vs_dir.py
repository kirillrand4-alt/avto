# -*- coding: utf-8 -*-
"""Даст ли СТАР/Saby что-то сверх checko — считаем по базе, а не рассуждаем.

Вопрос владельца прямой: у него есть вся база checko, значит платить за
справочник имеет смысл, только если тот отдаёт то, чего checko не даёт.

Две части.
1. Что checko УЖЕ дал: сколько компаний, сколько почт и телефонов, есть ли у
   них роли и есть ли ЛЮДИ. Это верхняя граница «и так есть».
2. Семь карточек saby, которые проверялись глазами: их маскированные адреса
   имеют читаемую форму (re**pt@, b**h@, i**o@), и по ней видно, что это за
   ящик. Смотрим, есть ли у нас уже почта на ТОМ ЖЕ домене и того же класса.
"""
import json
import re
import sys
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

db = EDB.EnrichDB()
e = db.cx
print(json.dumps({'старт': True}, ensure_ascii=False))

# --- 1. вклад checko
св = {}
for табл, поле in (('emails', 'email'), ('phone_contacts', 'phone')):
    строки = e.execute(
        f"SELECT count(*), count(distinct inn) FROM {табл} "
        "WHERE lower(source) LIKE '%checko%'").fetchone()
    ролей = e.execute(
        f"SELECT count(*) FROM {табл} WHERE lower(source) LIKE '%checko%' "
        "AND role NOT IN ('','общий')").fetchone()[0]
    св[табл] = {'строк': строки[0], 'компаний': строки[1],
                'с_осмысленной_ролью': ролей}
св['люди_из_checko'] = e.execute(
    "SELECT count(*) FROM people WHERE lower(source) LIKE '%checko%'").fetchone()[0]
св['все_источники_почт'] = [
    {'источник': r[0], 'шт': r[1]} for r in e.execute(
        'SELECT source, count(*) FROM emails GROUP BY 1 ORDER BY 2 DESC LIMIT 8')]

# --- 2. семь карточек saby: есть ли у нас уже такой адрес
КАРТОЧКИ = [
    ('7840346335', 'ilimgroup.ru', 'in ** ov'),
    ('5905016951', 'sodahlorat.com', 're ** pt'),
    ('7449006184', 'chkpz.ru', 'b ** h'),
    ('5001000041', 'linru.ru', 'i ** o'),
    ('3448027272', 'zirax.com', 'i ** o'),
    ('6230029069', 'tochinvest.ru', 'do ** et'),
    ('5007113179', 'bk.ru', 'vm ** 50'),
]
сверка = []
for inn, дом, маска in КАРТОЧКИ:
    наши = [{'почта': r[0], 'роль': r[1], 'источник': r[2]}
            for r in e.execute(
                'SELECT email, role, source FROM emails WHERE inn=?', (inn,))]
    на_домене = [x for x in наши if x['почта'].endswith('@' + дом)]
    нач, кон = [x.strip() for x in маска.split('**')]
    совпало = [x for x in на_домене
               if x['почта'].split('@')[0].startswith(нач)
               and x['почта'].split('@')[0].endswith(кон)]
    сверка.append({'инн': inn, 'маска_saby': маска + '@' + дом,
                   'наших_почт_всего': len(наши),
                   'на_том_же_домене': [x['почта'] for x in на_домене][:4],
                   'подходит_под_маску': [x['почта'] for x in совпало][:3]})
print(json.dumps({'сверка_карточек': сверка}, ensure_ascii=False)[:2400])
print(json.dumps(св, ensure_ascii=False))
