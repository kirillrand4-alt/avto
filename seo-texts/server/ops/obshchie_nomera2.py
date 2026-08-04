# -*- coding: utf-8 -*-
"""Общие номера в people — замер с раздельными ключами.

В прошлой попытке я сложил в один счётчик две разные группы («технические» и
«свежие»), и 242 + 66 не сошлись с 300. Считаю заново, каждой группе свой ключ.

ПРИЗНАК: один номер у двух и более разных людей одного предприятия — не личный.
Дополнительно смотрю номера, которые делят РАЗНЫЕ предприятия: такой номер не
принадлежит и предприятию тоже (колл-центр, холдинг, площадка).
"""
import sys, time
from collections import Counter, defaultdict
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

db = EDB.EnrichDB()
поля = {r[1] for r in db.cx.execute('PRAGMA table_info(people)')}
q = ("SELECT inn, COALESCE(person,''), COALESCE(post,''), COALESCE(role,''), "
     "COALESCE(phone,'')" +
     (", COALESCE(updated_at,'')" if 'updated_at' in поля else ", ''") +
     " FROM people WHERE COALESCE(phone,'')<>''")
строки = []
люди_на_номер = defaultdict(set)
инн_на_номер = defaultdict(set)
for инн, чел, пост, роль, тел, когда in db.cx.execute(q):
    ц = ''.join(c for c in str(тел) if c.isdigit())[-10:]
    if len(ц) < 6:
        continue
    инн, чел = str(инн), str(чел).strip().lower()
    люди_на_номер[(инн, ц)].add(чел)
    инн_на_номер[ц].add(инн)
    строки.append((инн, чел, str(пост), str(роль), ц, str(когда)))

делят_люди = {к for к, v in люди_на_номер.items() if len(v) >= 2}
делят_фирмы = {ц for ц, v in инн_на_номер.items() if len(v) >= 2}
ТЕХ = ('инженер', 'механик', 'энергетик', 'технич', 'производств', 'кипиа', 'метролог')
сегодня, вчера = time.strftime('%Y-%m-%d'), time.strftime(
    '%Y-%m-%d', time.localtime(time.time() - 86400))

в, т, с = Counter(), Counter(), Counter()
for инн, чел, пост, роль, ц, когда in строки:
    общий = (инн, ц) in делят_люди
    межфирменный = ц in делят_фирмы
    в['строк с телефоном'] += 1
    в['номер делят 2+ человека' if общий else 'номер уникален для человека'] += 1
    if межфирменный:
        в['номер стоит у РАЗНЫХ предприятий'] += 1
    if any(x in (пост + ' ' + роль).lower() for x in ТЕХ):
        т['технических с телефоном'] += 1
        т['   номер делят 2+ человека' if общий else '   номер уникален'] += 1
        if межфирменный:
            т['   номер стоит у разных предприятий'] += 1
    if когда.startswith(сегодня) or когда.startswith(вчера):
        с['принесено за сутки'] += 1
        с['   номер делят 2+ человека' if общий else '   номер уникален'] += 1

for гр in (в, т, с):
    for к, v in гр.items():
        print(f'{к:44} {v:6}')
    print()
