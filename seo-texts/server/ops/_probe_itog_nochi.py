# -*- coding: utf-8 -*-
"""Итог ночи честными числами: сколько целей обрели технического ЛПР.

Общая база покрывает только 748 предприятий с ДОКАЗАННЫМ фактом «центробежная
+ воздух», а работали мы по списку из 1486 без техЛПР, где 791 в доказанный
факт не входит. Поэтому прирост в базе и прирост по задаче — разные числа, и
показывать надо оба, иначе работа выглядит меньше, чем она есть.
"""
import csv
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)
csv.field_size_limit(10 ** 7)


def инны(имя, поле='inn'):
    п = os.path.join(ДРОП, имя)
    если = set()
    if not os.path.exists(п):
        return если
    for r in csv.DictReader(io.StringIO(
            open(п, encoding='utf-8-sig', errors='replace').read()),
            delimiter=';'):
        и = (r.get(поле) or '').strip()
        if и:
            если.add(и)
    return если


цели = инны('BEZ-TEHLPR-1486.csv')
база = инны('BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')

cx = EDB.EnrichDB().cx
сп = ','.join('?' * len(ТЕХ))
тех_строки = cx.execute(
    f"SELECT inn,person,COALESCE(post,''),role,COALESCE(source,''),"
    f"COALESCE(source_url,''),COALESCE(phone,'') FROM people "
    f'WHERE role IN ({сп})', tuple(ТЕХ)).fetchall()
тех_инн = {r[0] for r in тех_строки}

с_тел = {r[0] for r in тех_строки if r[6].strip()}
# телефон компании тоже считается зацепкой, но отдельно
с_тел_комп = set()
for и in (тех_инн & цели):
    if cx.execute('SELECT 1 FROM phone_contacts WHERE inn=? LIMIT 1',
                  (и,)).fetchone():
        с_тел_комп.add(и)

источники = Counter(r[4][:40] for r in тех_строки if r[0] in цели)
роли = Counter(r[3] for r in тех_строки if r[0] in цели)

print(json.dumps({
    'технических_людей_в_enrich_всего': len(тех_строки),
    'предприятий_с_техЛПР_всего': len(тех_инн),
    'целей_в_списке_1486': len(цели),
    'из_них_обрели_техЛПР': len(тех_инн & цели),
    'из_них_у_техЛПР_есть_личный_телефон': len(с_тел & цели),
    'из_них_есть_хотя_бы_телефон_предприятия': len(с_тел_комп),
    'предприятий_в_общей_базе': len(база),
    'из_них_с_техЛПР': len(тех_инн & база),
    'источники_техЛПР_по_целям': источники.most_common(12),
    'роли_техЛПР_по_целям': роли.most_common(),
}, ensure_ascii=False))
