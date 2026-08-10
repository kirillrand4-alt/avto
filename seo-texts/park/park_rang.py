# -*- coding: utf-8 -*-
"""РАНГ МАШИНЫ — первая ось порядка выдачи (решение владельца).
Цены нигде нет, ранжируем по признаку и ОБЯЗАТЕЛЬНО пишем каким (chem_rang):
A сумма из документа -> B кВт и м3/мин по опознанной модели -> C класс машины по серии
-> D+ срок ЭПБ истёк -> D класс опасности/давление -> E только тип."""
import sqlite3, csv, re, os, time
D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
cur.executescript("""
CREATE TABLE IF NOT EXISTS harakteristika(
  inn TEXT, marka TEXT, seriya TEXT, chto_eto TEXT,
  proizvoditelnost REAL, davlenie REAL, moshchnost REAL,
  ssylka TEXT, srok_sluzhby TEXT, vyvod TEXT,
  UNIQUE(inn, marka, proizvoditelnost, davlenie));
""")
def chislo(s):
    s = (s or '').replace(',', '.').strip()
    m = re.search(r'\d+(?:\.\d+)?', s)
    return float(m.group(0)) if m else None

n = 0
for r in csv.DictReader(open(os.path.join(D, 'HARAKTERISTIKI-mashin-po-predpriyatiyam.csv'),
                             encoding='utf-8-sig'), delimiter=';'):
    inn = (r.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn): continue
    cur.execute('insert or ignore into harakteristika values (?,?,?,?,?,?,?,?,?,?)',
                (inn, (r.get('marka') or '').strip(), (r.get('seriya') or '').strip(),
                 (r.get('chto_eto') or '').strip(), chislo(r.get('proizvoditelnost_m3min')),
                 chislo(r.get('davlenie')), chislo(r.get('moshchnost')),
                 (r.get('ssylka') or '').strip(), (r.get('srok_sluzhby') or '').strip(),
                 (r.get('vyvod_ekspertizy') or '').strip()))
    n += 1
p.commit()
print('характеристик влито:', n, '| в таблице:',
      cur.execute('select count(*) from harakteristika').fetchone()[0])

# ---- ПРИЗНАК B: мощность и производительность по опознанной марке ----------
# шкала: производительность м3/мин -> ранг. 250 м3/мин это машина на десятки млн.
def rang_po_proiz(q):
    if q is None: return None
    return 10 if q >= 200 else 9 if q >= 100 else 8 if q >= 50 else 7 if q >= 20 \
           else 6 if q >= 10 else 5 if q >= 5 else 4
def rang_po_kvt(w):
    if w is None: return None
    return 10 if w >= 4000 else 9 if w >= 1500 else 8 if w >= 630 else 7 if w >= 250 \
           else 6 if w >= 110 else 5 if w >= 45 else 4

B = 0
for inn, marka, q, w in cur.execute(
        'select inn,marka,proizvoditelnost,moshchnost from harakteristika '
        'where marka!="" and (proizvoditelnost is not null or moshchnost is not null)').fetchall():
    rg = max([x for x in (rang_po_proiz(q), rang_po_kvt(w)) if x is not None] or [0])
    if not rg: continue
    chem = 'B: %s%s по марке %s' % (
        ('%g м3/мин' % q) if q else '', (' / %g кВт' % w) if w else '', marka)
    r = cur.execute("update fakt set rang_mashiny=?, chem_rang=chem_rang||' | '||? "
                    "where inn=? and (model=? or marka=? or chto_naydeno like '%'||?||'%') "
                    "and (rang_mashiny is null or rang_mashiny < ?)",
                    (rg, chem, inn, marka, marka, marka, rg))
    B += r.rowcount
p.commit()
print('признак B (мощность/производительность) проставлен фактам:', B)

# ---- ПРИЗНАК D+: срок ЭПБ истёк — датировано документом --------------------
r = cur.execute("update fakt set rang_mashiny = coalesce(rang_mashiny, 6) "
                "where chem_rang like '%СРОК ИСТЁК%' and rang_mashiny is null")
p.commit(); print('признак D+ (срок ЭПБ истёк) проставлен:', r.rowcount)

# ---- ПРИЗНАК A: сумма из документа ----------------------------------------
A = 0
for fid, s in cur.execute("select id,summa from fakt where summa!='' and rang_mashiny is null").fetchall():
    v = chislo(s)
    if not v: continue
    rg = 10 if v >= 5e7 else 9 if v >= 2e7 else 8 if v >= 5e6 else 7 if v >= 1e6 else 5
    cur.execute("update fakt set rang_mashiny=?, chem_rang=chem_rang||' | A: сумма '||? where id=?",
                (rg, s, fid)); A += 1
p.commit(); print('признак A (сумма из документа) проставлен:', A)

# ---- ПРИЗНАК E: известен только тип ---------------------------------------
r = cur.execute("update fakt set rang_mashiny=2, chem_rang=chem_rang||' | E: известен только тип' "
                "where rang_mashiny is null and tip!='' and tip!='НЕ НАША МАШИНА'")
p.commit(); print('признак E (только тип) проставлен:', r.rowcount)

print()
print('=== ПОКРЫТИЕ РАНГОМ ===')
print('  фактов с рангом:', cur.execute('select count(*) from fakt where rang_mashiny is not null').fetchone()[0])
print('  ИНН с рангом:', cur.execute('select count(distinct inn) from fakt where rang_mashiny is not null').fetchone()[0])
print()
print('=== ТОП-15 ПРЕДПРИЯТИЙ по правилу владельца: машина дороже + лучшая тех роль ===')
for r in cur.execute("""
  select f.inn,
         coalesce(nullif(f.nazvanie,''), (select name from spravochnik s where s.inn=f.inn)),
         max(f.rang_mashiny), min(f.sila), count(*),
         (select min(rang) from kontakt k where k.inn=f.inn and k.rang<=2),
         (select count(*) from kontakt k where k.inn=f.inn)
  from fakt f where f.rang_mashiny is not null and f.tip!='НЕ НАША МАШИНА'
  group by f.inn order by max(f.rang_mashiny) desc, min(f.sila) asc, count(*) desc limit 15""").fetchall():
    print('  %-12s %-34s ранг=%-4s сила=%s фактов=%-5s круг=%-4s конт=%s' %
          (r[0], (r[1] or '')[:34], r[2], r[3], r[4], r[5] if r[5] else '—', r[6]))
p.close()
