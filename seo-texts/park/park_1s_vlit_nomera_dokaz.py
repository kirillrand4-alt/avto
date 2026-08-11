# -*- coding: utf-8 -*-
"""Принимает журнал доказательств личных номеров в park.db — чтобы панель могла их показать.

Владелец просит в панели фильтр «со скриншотом доказательства, где видно номер, должность и
ФИО». Снимки делает `park_1s_snimok_nomera.py` на сервере, вердикт пишет в
`park_nomera_dokaz.jsonl`. Здесь журнал переносится в таблицу `nomer_dokaz`, откуда сборка
панели кладёт имя снимка рядом с предприятием.

Берётся ПОСЛЕДНИЙ вердикт по паре (ИНН, номер): прибор чинился по ходу, и ранние строки
писались сломанной версией — если брать первую, в панель уедет старая правда.

В панель идёт только `ДОКАЗАНО` — то есть на снимке видны И номер, И фамилия. Записи
«номер есть, чей не ясно», «номера на странице нет», «склейка» остаются в таблице со своим
вердиктом, но фильтр их не показывает: владелец просил снимок, на котором ВИДНО, а не любой.
"""
import json, os, sqlite3, sys, time

D = os.path.dirname(os.path.abspath(__file__))
FAYL = sys.argv[1] if len(sys.argv) > 1 else 'PARK-NOMERA-DOKAZ-1S.jsonl'
if not os.path.isabs(FAYL):
    FAYL = os.path.join(D, FAYL)
if not os.path.exists(FAYL):
    raise SystemExit('нет журнала: %s' % FAYL)

p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
c.execute("""create table if not exists nomer_dokaz(
    inn text, nomer text, chelovek text, dolzhnost text, snimok text,
    vyvod text, dokazano integer, ssylka text, citata text, ts text,
    primary key(inn, nomer))""")

poslednie = {}
vsego = 0
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    x = json.loads(ln)
    vsego += 1
    poslednie[(x.get('inn'), x.get('nomer'))] = x      # последний вердикт побеждает

bylo = c.execute('select count(*) from nomer_dokaz').fetchone()[0]
for (inn, nomer), x in poslednie.items():
    dok = 1 if (x.get('vyvod') or '').startswith('ДОКАЗАНО') else 0
    c.execute('insert or replace into nomer_dokaz values (?,?,?,?,?,?,?,?,?,?)',
              (inn, nomer, x.get('chelovek'), x.get('dolzhnost'), x.get('snimok'),
               x.get('vyvod'), dok, x.get('ssylka'), (x.get('citata') or '')[:400],
               time.strftime('%Y-%m-%d %H:%M:%S')))
stalo = c.execute('select count(*) from nomer_dokaz').fetchone()[0]
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'НОМЕРА: доказательство снимком',
           vsego, len(poslednie), vsego - len(poslednie),
           'последний вердикт по паре (ИНН, номер); в панель идёт только ДОКАЗАНО'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print('строк в журнале ................ %d' % vsego)
print('уникальных (ИНН, номер) ........ %d' % len(poslednie))
print('в таблице было %d, стало %d' % (bylo, stalo))
print()
print('ДОКАЗАНО (номер и фамилия видны) %d' % q('select count(*) from nomer_dokaz where dokazano=1'))
print('  предприятий с доказанным номером %d'
      % q('select count(distinct inn) from nomer_dokaz where dokazano=1'))
print('прочие вердикты:')
for v, n in c.execute("""select vyvod, count(*) from nomer_dokaz where dokazano=0
                          group by vyvod order by 2 desc limit 6"""):
    print('   %-52s %d' % ((v or '')[:52], n))
p.close()
