# -*- coding: utf-8 -*-
"""Тот же заслон общих номеров, что стоит в enrich, — теперь и в p25.contact.

ПОВОД. Файл `P25-LYUDI-2S-017.csv` привязал `+7 495 664-88-40` к ДВЕНАДЦАТИ
разным людям одного предприятия. 3-я сессия в сопроводительном письме прямо
пишет, что это линия ЭТП ГПБ, а не чей-то стол. В enrich.people такой заслон я
уже поставил (1019 строк помечено), в p25 его не было — дыра ровно того же
рода, что и «пометка сомнения, которую приёмка не читала».

ПРИЗНАКИ, оба без догадок:
   один номер у 2+ разных людей ОДНОГО предприятия — не личный;
   один номер у 2+ РАЗНЫХ предприятий — не принадлежит и предприятию.

Помечаю, не удаляю: номер настоящий, неверен только ярлык «личный».
Запуск: python p25_pometit_obshchie.py [--apply]
"""
import io, json, os, sqlite3, sys, time
from collections import Counter, defaultdict

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_obshchie_nomera.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv

цб = sqlite3.connect(P25, timeout=30)
поля = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
if 'nomer_ne_lichnyy' not in поля:
    if ПРИМЕНИТЬ:
        цб.execute('ALTER TABLE contact ADD COLUMN nomer_ne_lichnyy TEXT')
        цб.commit()
        print('колонка nomer_ne_lichnyy заведена в p25.contact')
    else:
        print('колонки нет — будет заведена при --apply')

люди = defaultdict(set)
фирмы = defaultdict(set)
строки = []
for rid, инн, чел, зн, вид in цб.execute(
        "SELECT rowid, inn, COALESCE(person,''), COALESCE(value,''), "
        "COALESCE(kind,'') FROM contact"):
    if str(вид) and str(вид) != 'phone':
        continue
    ц = ''.join(c for c in str(зн) if c.isdigit())[-10:]
    if len(ц) < 6:
        continue
    ч = str(чел).strip().casefold()
    if ч:
        люди[(str(инн), ц)].add(ч)
    фирмы[ц].add(str(инн))
    строки.append((rid, str(инн), ч, ц))

стат = Counter()
метки = []
for rid, инн, ч, ц in строки:
    много_людей = len(люди.get((инн, ц), ())) >= 2
    много_фирм = len(фирмы[ц]) >= 2
    if много_фирм:
        метки.append((rid, 'номер стоит у %d разных предприятий — не принадлежит '
                           'и этому' % len(фирмы[ц])))
        стат['помечено: номер у разных предприятий'] += 1
    elif много_людей:
        метки.append((rid, 'номер делят %d человека этого предприятия — это отдел, '
                           'линия или приёмная' % len(люди[(инн, ц)])))
        стат['помечено: делят люди одного предприятия'] += 1
    else:
        стат['номер уникален — не трогаю'] += 1

for к, v in стат.items():
    print(f'{к:52} {v:6}')

if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН')
    цб.close()
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
for rid, не in метки:
    цб.execute('UPDATE contact SET nomer_ne_lichnyy=? WHERE rowid=?', (не, rid))
цб.commit()
всего = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
чистых = цб.execute("SELECT COUNT(*) FROM contact WHERE COALESCE(nomer_ne_lichnyy,'')=''"
                    " AND COALESCE(person,'')<>''").fetchone()[0]
цб.close()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for rid, не in метки:
        ф.write(json.dumps({'rowid': rid, 'prichina': не, 'ts': ts},
                           ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())
print()
print(f'помечено строк                          {len(метки):6}')
print(f'контактов всего                         {всего:6}')
print(f'с названным человеком и своим номером    {чистых:6}')
