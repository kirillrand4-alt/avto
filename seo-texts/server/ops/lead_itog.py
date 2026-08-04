# -*- coding: utf-8 -*-
"""Итог прохода по руководству — по потоку и по базе, а не по обрезанному stdout."""
import io, json, os, sqlite3, sys
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

П = r'C:\seostat\drop\p25_leadership_stream.jsonl'
строки = []
for s in io.open(П, encoding='utf-8', errors='replace'):
    s = s.strip()
    if s:
        try:
            строки.append(json.loads(s))
        except Exception:
            pass
c = Counter()
c['целей пройдено'] = len(строки)
for з in строки:
    c['с ошибкой'] += 1 if з.get('err') else 0
    c['людей найдено'] += int(з.get('людей') or 0)
    c['с телефоном'] += int(з.get('с_телефоном') or з.get('телефонов') or 0)
    c['техЛПР'] += int(з.get('техЛПР') or 0)
for к, v in c.items():
    print(f'{к:28} {v:6}')

db = EDB.EnrichDB()
поля = {r[1] for r in db.cx.execute('PRAGMA table_info(people)')}
print()
print('В БАЗЕ people, роль + телефон (последние 12 по времени):')
где = "COALESCE(phone,'')<>''" if 'phone' in поля else "1=1"
q = ("SELECT inn, person, COALESCE(post,''), COALESCE(role,''), "
     "COALESCE(phone,''), COALESCE(source_url,'') FROM people "
     f"WHERE {где} AND COALESCE(role,'') NOT IN ('','общий') "
     "ORDER BY rowid DESC LIMIT 12")
try:
    for р in db.cx.execute(q):
        print(f"   {р[0]:12} {str(р[1])[:26]:26} {str(р[2])[:22]:22} {str(р[4])[:18]}")
except Exception as e:
    print('   не смог выбрать:', type(e).__name__, str(e)[:90])

тех = db.cx.execute(
    "SELECT COUNT(*) FROM people WHERE COALESCE(role,'') IN "
    "('гл.инженер','гл.механик','гл.энергетик','главный инженер','техдиректор')"
).fetchone()[0]
тех_тел = db.cx.execute(
    "SELECT COUNT(*) FROM people WHERE COALESCE(phone,'')<>'' AND COALESCE(role,'') IN "
    "('гл.инженер','гл.механик','гл.энергетик','главный инженер','техдиректор')"
).fetchone()[0]
print()
print(f'{"технических людей в enrich.people":40} {тех:6}')
print(f'{"   из них с телефоном":40} {тех_тел:6}')
