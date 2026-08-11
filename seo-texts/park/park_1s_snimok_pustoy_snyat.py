# -*- coding: utf-8 -*-
"""Снимает доказанность с тех номеров, чей снимок оказался пустым листом.

Прибор `park_1s_snimok_chernila.py` посчитал долю не-белых точек по всем 99 снимкам и положил
итог на дроп. Здесь этот итог принимается в park.db и применяется к вердиктам: если на
картинке ноль чернил — доказательства нет, каким бы уверенным ни был текстовый разбор.

Числа держатся в таблице `snimok_kachestvo` (durability): по ней потом видно, какой кадр
переснимали и чем кончилось, а не только «сколько сейчас доказано».

Запуск: python3 park_1s_snimok_pustoy_snyat.py [--pisat]
"""
import json
import os
import sqlite3
import subprocess
import sys
import time

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
KLIENT = '/home/user/avto/seo-texts/server/drop_client.sh'
FAYL = 'PARK-SNIMKI-CHERNILA.json'

put = os.path.join(D, FAYL)
if not os.path.exists(put) or '--zanovo' in sys.argv:
    subprocess.run(['bash', KLIENT, 'down', FAYL], capture_output=True, timeout=600, cwd=D)
zamery = json.load(open(put, encoding='utf-8'))

p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
c.execute("""create table if not exists snimok_kachestvo(
    imya text primary key, inn text, nomer text, bayt integer, chernila real,
    pustoy integer, ts text)""")

bylo_dok = c.execute('select count(*) from nomer_dokaz where dokazano=1').fetchone()[0]
snyato, pustyh_vsego, ne_nashlos = [], 0, 0
for z in zamery:
    if z.get('pustoy'):
        pustyh_vsego += 1
    c.execute('insert or replace into snimok_kachestvo values (?,?,?,?,?,?,?)',
              (z['imya'], z.get('inn'), z.get('nomer'), z.get('bayt'), z.get('chernila'),
               z.get('pustoy'), time.strftime('%Y-%m-%d %H:%M:%S')))
    if not z.get('pustoy') or not z.get('inn'):
        continue
    r = c.execute("""select dokazano, coalesce(chelovek,''), coalesce(vyvod,'')
                       from nomer_dokaz where inn=? and nomer like ?""",
                  (z['inn'], '%' + z['nomer'][-10:])).fetchone()
    if not r:
        ne_nashlos += 1
        continue
    if r[0] == 1:
        snyato.append((z['inn'], z['nomer'], r[1]))
    c.execute("""update nomer_dokaz set dokazano=0,
                        vyvod='снимок пустой (' || ? || ' б): показать номер нечем'
                  where inn=? and nomer like ?""",
              (z.get('bayt'), z['inn'], '%' + z['nomer'][-10:]))

print('замеров принято: %d | пустых кадров: %d | строки в вердиктах не нашлось: %d'
      % (len(zamery), pustyh_vsego, ne_nashlos))
print('снимается доказанность (кадр пустой, а стояло «доказано»): %d' % len(snyato))
for inn, nom, chel in snyato:
    print('   %-11s %-11s %s' % (inn, nom, chel[:40]))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'СНИМКИ: пустой кадр не доказательство',
           len(zamery), pustyh_vsego, len(snyato),
           'мерка — доля не-белых точек в самом PNG, а не наличие файла'))
p.commit()
stalo = c.execute('select count(*) from nomer_dokaz where dokazano=1').fetchone()[0]
print()
print('доказано номеров: было %d, стало %d' % (bylo_dok, stalo))
p.close()
