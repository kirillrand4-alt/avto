# -*- coding: utf-8 -*-
"""Словарь серий 3-й сессии -> park.db. Серия питает и полноту (ОХВАТ), и ось цены
(признак C ранга машины): принцип работы задаёт класс машины."""
import sqlite3, csv, os, time, json
D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS seriya(
  seriya TEXT PRIMARY KEY, princip TEXT, vid TEXT,
  vstrech INTEGER, innov INTEGER, ssylok INTEGER, klass_ceny INTEGER, citata TEXT);
CREATE TABLE IF NOT EXISTS seriya_ssylka(
  seriya TEXT, url TEXT, UNIQUE(seriya, url));
""")
# класс машины для оси цены: чем крупнее машина, тем выше класс
KLASS = {('центробежный', 'компрессор'): 5, ('центробежный', 'нагнетатель'): 5,
         ('центробежный', 'ГПА'): 5, ('центробежный', 'воздуходувка'): 3,
         ('винтовой', 'компрессор'): 3, ('поршневой', 'компрессор'): 2,
         ('не установлен', 'компрессор'): 2}
n = ss = 0
for r in csv.DictReader(open(os.path.join(D, 'PARK-SLOVAR-SERII-3S.csv'),
                             encoding='utf-8-sig'), delimiter=';'):
    ser = (r['seriya'] or '').strip()
    if not ser: continue
    vid, pr = (r['vid'] or '').strip(), (r['princip'] or '').strip()
    kl = KLASS.get((pr, vid), 4 if vid in ('ВРУ', 'генератор азота/кислорода', 'МКС') else 2)
    cur.execute('insert or replace into seriya values (?,?,?,?,?,?,?,?)',
                (ser, pr, vid, int(r['vstrech'] or 0), int(r['innov'] or 0),
                 int(r['ssylok'] or 0), kl, (r['citata'] or '')[:400]))
    n += 1
    for u in (r.get('ssylki') or '').split('|'):
        u = u.strip()
        if u.startswith('http'):
            cur.execute('insert or ignore into seriya_ssylka values (?,?)', (ser, u)); ss += 1
cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'PARK-SLOVAR-SERII-3S.csv (словарь серий)',
             n, n, 0, 'серии + ссылки-доказательства серии'))
p.commit()
print('серий влито %s, ссылок серий %s' % (n, cur.execute('select count(*) from seriya_ssylka').fetchone()[0]))

# ПРИМЕНЕНИЕ 1: проставить принцип и класс машине там, где модель совпала с серией
cur.execute("""update fakt set sreda=sreda where 1=0""")
sovpalo = 0
for ser, pr, vid, kl in cur.execute('select seriya,princip,vid,klass_ceny from seriya'):
    r = cur.execute("update fakt set chem_rang = chem_rang || ' | серия ' || ? || ' (' || ? || ')', "
                    "rang_mashiny = coalesce(rang_mashiny, ?) "
                    "where (model=? or model like ?||'%' or chto_naydeno like '%'||?||'%') "
                    "and (rang_mashiny is null)", (ser, pr, kl, ser, ser, ser))
    sovpalo += r.rowcount
p.commit()
print('фактов, которым серия проставила класс машины:', sovpalo)
print('--- покрытие словарём ---')
print('  фактов с рангом машины:', cur.execute('select count(*) from fakt where rang_mashiny is not null').fetchone()[0])
print('  ИНН с рангом:', cur.execute('select count(distinct inn) from fakt where rang_mashiny is not null').fetchone()[0])
for r in cur.execute('select rang_mashiny,count(*),count(distinct inn) from fakt '
                     'where rang_mashiny is not null group by 1 order by 1 desc'):
    print('  класс %s: строк=%-6s ИНН=%s' % r)
p.close()
