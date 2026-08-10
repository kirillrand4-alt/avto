# -*- coding: utf-8 -*-
"""ВЫДАЧА по предприятиям — продукт задачи. Порядок задан владельцем:
машина = фильтр -> ранг машины (дороже выше) -> ранг контакта (лучшая тех роль)."""
import sqlite3, os, csv, time
D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()
cur.executescript("""
DROP TABLE IF EXISTS predpriyatie;
CREATE TABLE predpriyatie(
  inn TEXT PRIMARY KEY, nazvanie TEXT, region TEXT, okved TEXT, vyruchka TEXT,
  status_egrul TEXT,
  rang_mashiny REAL, sila_luchshaya INTEGER, faktov INTEGER, ssylok INTEGER,
  tipy TEXT, marki TEXT, zav_nomerov INTEGER,
  srok_epb_istek INTEGER, sostoyaniya TEXT,
  chelovek TEXT, dolzhnost TEXT, krug INTEGER,
  telefon TEXT, telefon_lichnyy INTEGER, mobilnyy INTEGER, pochta TEXT,
  kontaktov INTEGER, ssylka_luchshaya TEXT, ts TEXT);
""")
cur.execute("""
INSERT INTO predpriyatie
SELECT f.inn,
  -- имя предприятия: сначала справочник (ЕГРЮЛ), потом САМОЕ ЧАСТОЕ имя в фактах.
  -- Было max(nazvanie) — алфавитный максимум: у ИНН 5103070023 он брал «Балаковские
  -- Минудобрения» (1 упоминание) вместо «АО "АПАТИТ"» (90). Так ошиблись 41 предприятие.
  -- 461 предприятие парка стояло вовсе без имени: машина доказана, а звонить некуда
  -- даже по названию. Имя, адрес, руководителя и статус взяли из ЕГРЮЛ (dadata) —
  -- таблица egrul, она же даёт «ликвидировано», чтобы не звонить в пустоту.
  coalesce(
    (select nullif(s.name_obzvon,'') from spravochnik s where s.inn=f.inn),
  -- Вливание ЕИС принесло полные ЕГРЮЛ-имена («ОБЩЕСТВО С ОГРАНИЧЕННОЙ
  -- ОТВЕТСТВЕННОСТЬЮ …»), и они стали самыми частыми — в выдаче вместо
  -- «ООО "ГАЗПРОМ НЕФТЕХИМ САЛАВАТ"» появилось обрезанное «ОБЩЕСТВО С ОГРАНИЧЕННОЙ
  -- ОТВЕТС». Поэтому сначала ищем КОРОТКУЮ форму: аббревиатура плюс кавычки.
    (select x.nazvanie from fakt x where x.inn=f.inn and x.nazvanie<>''
       and length(x.nazvanie)<=70
       and (x.nazvanie like 'ООО%' or x.nazvanie like 'АО%' or x.nazvanie like 'ПАО%'
            or x.nazvanie like 'ЗАО%' or x.nazvanie like 'ОАО%' or x.nazvanie like 'АК%'
            or x.nazvanie like 'НАО%' or x.nazvanie like 'ФГУП%' or x.nazvanie like 'ГУП%')
       group by x.nazvanie order by count(*) desc, length(x.nazvanie) asc limit 1),
    (select nullif(e.imya,'') from egrul e where e.inn=f.inn),
    (select nullif(i.imya,'') from imya_eis i where i.inn=f.inn),
    (select x.nazvanie from fakt x where x.inn=f.inn and x.nazvanie<>''
       group by x.nazvanie order by count(*) desc, length(x.nazvanie) desc limit 1)),
  (select region from spravochnik s where s.inn=f.inn),
  (select okved from spravochnik s where s.inn=f.inn),
  (select revenue_rub from spravochnik s where s.inn=f.inn),
  coalesce((select nullif(s.egrul_status,'') from spravochnik s where s.inn=f.inn),
           (select nullif(e.status,'') from egrul e where e.inn=f.inn)),
  max(f.rang_mashiny), min(f.sila), count(*),
  (select count(*) from fakt_ssylka s join fakt g on g.id=s.fakt_id where g.inn=f.inn),
  (select group_concat(t,' | ') from (select distinct tip t from fakt x
      where x.inn=f.inn and x.v_parke=1 and x.tip<>'' order by t)),
  (select group_concat(m,' | ') from (select distinct model m from fakt x
      where x.inn=f.inn and x.v_parke=1 and x.model<>'' limit 8)),
  (select count(*) from fakt x where x.inn=f.inn and x.zavodskoy_nomer<>''),
  (select count(*) from fakt x where x.inn=f.inn and x.chem_rang like '%ИСТЁК%'),
  (select group_concat(s2,' | ') from (select distinct sostoyanie s2 from fakt x
      where x.inn=f.inn and x.v_parke=1 and x.sostoyanie<>'')),
  (select person from contact_source c where c.inn=f.inn and c.person<>''
     order by case when c.dolzhnost like '%лавн%инженер%' or c.dolzhnost like '%лавн%механик%'
                     or c.dolzhnost like '%лавн%энергетик%' then 1
                   when c.dolzhnost like '%ачальник%' or c.dolzhnost like '%нженер%' then 2
                   when c.dolzhnost<>'' then 3 else 4 end limit 1),
  (select dolzhnost from contact_source c where c.inn=f.inn and c.dolzhnost<>''
     order by case when c.dolzhnost like '%лавн%инженер%' or c.dolzhnost like '%лавн%механик%'
                     or c.dolzhnost like '%лавн%энергетик%' then 1
                   when c.dolzhnost like '%ачальник%' or c.dolzhnost like '%нженер%' then 2
                   else 3 end limit 1),
  (select min(rang) from kontakt k where k.inn=f.inn),
  -- правило владельца: контакт без ссылки за доказанный не выдаётся.
  -- Замер: 8 предприятий получали телефон с нулём ссылок, 2 — такую же почту.
  (select znachenie from kontakt k where k.inn=f.inn and k.vid='telefon' and k.ssylok>0
     order by k.rang, k.lichnyy desc, k.mobilnyy desc, k.ssylok_pervoistochnik desc limit 1),
  (select max(lichnyy) from kontakt k where k.inn=f.inn and k.vid='telefon'),
  (select max(mobilnyy) from kontakt k where k.inn=f.inn and k.vid='telefon'),
  (select znachenie from kontakt k where k.inn=f.inn and k.vid='email' and k.ssylok>0
     order by k.rang, k.lichnyy desc, k.ssylok_pervoistochnik desc limit 1),
  (select count(*) from kontakt k where k.inn=f.inn),
  (select s.url from fakt_ssylka s join fakt g on g.id=s.fakt_id
     where g.inn=f.inn order by s.pervoistochnik desc, g.sila limit 1),
  ?
FROM fakt f WHERE f.v_parke=1 GROUP BY f.inn""", (time.strftime('%Y-%m-%d %H:%M:%S'),))
p.commit()
cur.execute("alter table predpriyatie add column os text default ''") if 'os' not in [
    r[1] for r in cur.execute('pragma table_info(predpriyatie)').fetchall()] else None
cur.execute("""update predpriyatie set os = case
   when inn in (select distinct inn from fakt where v_parke=1
                and coalesce(vid_fakta,'') in ('машина','узел','расходник'))
        and inn in (select distinct inn from fakt where vid_fakta='газ')
        then 'парк машин + расход газа'
   when inn in (select distinct inn from fakt where vid_fakta='газ')
        then 'расход газа (машины нет)'
   else 'парк машин' end""")
p.commit()
q = lambda s: cur.execute(s).fetchone()[0]
print('предприятий в выдаче:', q('select count(*) from predpriyatie'))

# ---- выгрузка в CSV в ПОРЯДКЕ ВЛАДЕЛЬЦА -----------------------------------
POLYA = ['inn','nazvanie','os','status_egrul','region','rang_mashiny','sila_luchshaya','faktov','ssylok','tipy',
         'marki','zav_nomerov','srok_epb_istek','sostoyaniya','chelovek','dolzhnost','krug',
         'telefon','telefon_lichnyy','mobilnyy','pochta','kontaktov','vyruchka','okved',
         'ssylka_luchshaya']
rows = cur.execute("""select %s from predpriyatie
  order by rang_mashiny desc, sila_luchshaya asc,
           case when krug is null then 9 else krug end asc,
           mobilnyy desc, faktov desc""" % ','.join(POLYA)).fetchall()
with open(os.path.join(D, 'PARK-VYDACHA-PREDPRIYATIYA.csv'), 'w', encoding='utf-8-sig',
          newline='') as f:
    w = csv.writer(f, delimiter=';'); w.writerow(POLYA)
    for r in rows: w.writerow(['' if x is None else x for x in r])
print('CSV выложен, строк:', len(rows))
print()
print('=== МЕРЫ ЗАДАЧИ (раздел 6 стартового файла) ===')
print('  1. предприятий с машиной класса 1-3      ', q("select count(*) from predpriyatie where sila_luchshaya<=3"))
print('  2. из них с ТЕХКОНТАКТОМ (круг 1-2)      ', q("select count(*) from predpriyatie where sila_luchshaya<=3 and krug<=2"))
print('     из них с личным мобильным             ', q("select count(*) from predpriyatie where sila_luchshaya<=3 and krug<=2 and mobilnyy=1"))
print('  3. «покупает газ / арендует» (N2,O2,МКС) ', q("select count(*) from predpriyatie where sostoyaniya like '%покупает ГАЗ%' or sostoyaniya like '%арендует%'"))
print()
print('=== ТОП-12 ВЫДАЧИ ===')
for r in cur.execute("""select inn,substr(nazvanie,1,30),rang_mashiny,sila_luchshaya,faktov,
   krug,substr(coalesce(chelovek,'—'),1,22),coalesce(telefon,'—')
   from predpriyatie order by rang_mashiny desc, sila_luchshaya asc,
   case when krug is null then 9 else krug end, mobilnyy desc, faktov desc limit 12"""):
    print('  %-12s %-30s ранг=%-4s сила=%s фактов=%-4s круг=%-3s %-22s %s' %
          (r[0], r[1], r[2], r[3], r[4], r[5] if r[5] else '—', r[6], r[7]))
p.close()
