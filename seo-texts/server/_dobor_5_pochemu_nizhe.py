# -*- coding: utf-8 -*-
"""Почему доля находок ниже замера: не выбрали ли богатых соседние процессы.

Берём те же 260 компаний замера и смотрим: у кого контакты появились ПОСЛЕ
замера (значит, из моей очереди они выбыли), и какая у них была находимость.
Только чтение.
"""
import json
import sqlite3

RO = 'file:C:/sender/enrich.db?mode=ro'
d = json.load(open(r'C:\sender\_tmp\dyra3.json', encoding='utf-8'))
vyb = [r for r in d['vyborka'] if 'err' not in r]
c = sqlite3.connect(RO, uri=True, timeout=60)
est_teper = set()
for r in vyb:
    n = c.execute('select (select count(*) from emails where inn=?) '
                  '+ (select count(*) from phone_contacts where inn=?)',
                  (r['inn'], r['inn'])).fetchone()[0]
    if n:
        est_teper.add(r['inn'])
# кто из них получил контакты НЕ от нас
nashi = {str(r[0]) for r in c.execute(
    "select distinct inn from emails where coalesce(pometka,'') like '%кэш-добор%'")}
nashi |= {str(r[0]) for r in c.execute(
    "select distinct inn from phone_contacts where source like 'кэш-добор%'")}
istochniki = {}
for r in c.execute(
        "select coalesce(source,''), count(distinct inn) from phone_contacts "
        "where inn in (select inn from phone_contacts) group by 1 order by 2 desc limit 6"):
    istochniki[r[0]] = r[1]
c.close()

ushli = [r for r in vyb if r['inn'] in est_teper and r['inn'] not in nashi]
ostalis = [r for r in vyb if r['inn'] not in est_teper or r['inn'] in nashi]


def doli(g, imya):
    if not g:
        print(imya, '— пусто')
        return
    p = sum(1 for r in g if r['pocht'])
    t = sum(1 for r in g if r['tel'])
    print('%s: %d компаний | с почтой %d (%.1f%%) | с телефоном %d (%.1f%%) | '
          'почт всего %d, телефонов %d'
          % (imya, len(g), p, 100.0 * p / len(g), t, 100.0 * t / len(g),
             sum(r['pocht'] for r in g), sum(r['tel'] for r in g)))


print('выборка замера:', len(vyb))
doli(vyb, 'ВСЕ 260 (замер)')
doli(ushli, 'ВЫБЫЛИ (контакты дали другие процессы)')
doli(ostalis, 'ОСТАЛИСЬ в моей очереди')
print('источники телефонов в базе (компаний):', json.dumps(istochniki, ensure_ascii=False)[:400])
