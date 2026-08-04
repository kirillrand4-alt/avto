# -*- coding: utf-8 -*-
"""Пометить в people номера, которые не могут быть личными.

ПОЧЕМУ ПОМЕТКА, А НЕ УДАЛЕНИЕ. Правило владельца «разделять, а не отсеивать»:
номер настоящий и предприятию принадлежит, неверно лишь то, что он ЛИЧНЫЙ.
Удалить значит потерять добытое; оставить как есть — испортить меру ТЗ
(«личный мобильный технаря»), потому что приёмная посчитается за личный.

ДВА ПРИЗНАКА, ОБА БЕЗ ДОГАДОК
    1  один номер у 2+ разных людей одного предприятия — не личный;
    2  один номер у 2+ РАЗНЫХ предприятий — не принадлежит и предприятию
       (колл-центр, холдинг, площадка-посредник).

Колонка добавляется, ничего не переписывается. Запуск: python pometit_obshchie.py [--apply]
"""
import io, json, os, sys, time
from collections import Counter, defaultdict
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

ПОТОК = r'C:\seostat\drop\people_obshchie_nomera.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv

db = EDB.EnrichDB()
поля = {r[1] for r in db.cx.execute('PRAGMA table_info(people)')}
if 'nomer_ne_lichnyy' not in поля:
    if ПРИМЕНИТЬ:
        db.cx.execute('ALTER TABLE people ADD COLUMN nomer_ne_lichnyy TEXT')
        db.cx.commit()
        print('колонка nomer_ne_lichnyy заведена')
    else:
        print('колонки nomer_ne_lichnyy нет — будет заведена при --apply')

люди_на_номер = defaultdict(set)
инн_на_номер = defaultdict(set)
строки = []
for rid, инн, чел, тел in db.cx.execute(
        "SELECT rowid, inn, COALESCE(person,''), COALESCE(phone,'') FROM people "
        "WHERE COALESCE(phone,'')<>''"):
    ц = ''.join(c for c in str(тел) if c.isdigit())[-10:]
    if len(ц) < 6:
        continue
    люди_на_номер[(str(инн), ц)].add(str(чел).strip().lower())
    инн_на_номер[ц].add(str(инн))
    строки.append((rid, str(инн), str(чел), ц))

стат = Counter()
метки = []
for rid, инн, чел, ц in строки:
    много_людей = len(люди_на_номер[(инн, ц)]) >= 2
    много_фирм = len(инн_на_номер[ц]) >= 2
    if не := ('номер стоит у %d разных предприятий — не принадлежит и этому'
              % len(инн_на_номер[ц]) if много_фирм else
              ('номер делят %d человека этого предприятия — это отдел или приёмная'
               % len(люди_на_номер[(инн, ц)]) if много_людей else '')):
        метки.append((rid, не))
        стат['помечено: у разных предприятий' if много_фирм
             else 'помечено: делят люди одного предприятия'] += 1
    else:
        стат['номер уникален — не трогаю'] += 1

for к, v in стат.items():
    print(f'{к:52} {v:6}')

if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН')
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
for rid, не in метки:
    db.cx.execute('UPDATE people SET nomer_ne_lichnyy=? WHERE rowid=?', (не, rid))
db.cx.commit()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for rid, не in метки:
        ф.write(json.dumps({'rowid': rid, 'prichina': не, 'ts': ts},
                           ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())

тех_личных = db.cx.execute(
    "SELECT COUNT(*) FROM people WHERE COALESCE(phone,'')<>'' "
    "AND COALESCE(nomer_ne_lichnyy,'')='' AND ("
    "LOWER(COALESCE(post,'')) LIKE '%инженер%' OR LOWER(COALESCE(post,'')) LIKE '%механик%' "
    "OR LOWER(COALESCE(post,'')) LIKE '%энергетик%')").fetchone()[0]
print()
print(f'помечено строк                                  {len(метки):6}')
print(f'технических с номером, который может быть личным {тех_личных:6}')
