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
  -- ВИТРИНА ПРОТИВ БАЗЫ. 3-я сессия посчитала по выложенной выгрузке: с ОКВЭД 356,
  -- с выручкой 914, а я в панели показываю 2 482 и 1 474. Разрыв не в выгрузке файла,
  -- а здесь: выдача брала ОКВЭД и выручку ТОЛЬКО из справочника обзвона, тогда как
  -- панель сшивает их из finansy (реквизиты checko/dadata, ЕГРЮЛ) и лишь потом из
  -- справочника. Соседи работают по выгрузке — значит и выгрузка обязана видеть всё.
  coalesce((select nullif(x.okved,'') from finansy x where x.inn=f.inn),
           (select nullif(s.okved,'') from spravochnik s where s.inn=f.inn),
           (select nullif(e.okved,'') from egrul e where e.inn=f.inn)),
  coalesce((select nullif(cast(x.vyruchka as real),0) from finansy x where x.inn=f.inn),
           (select nullif(cast(s.revenue_rub as real),0) from spravochnik s where s.inn=f.inn)),
  coalesce((select nullif(s.egrul_status,'') from spravochnik s where s.inn=f.inn),
           (select nullif(e.status,'') from egrul e where e.inn=f.inn)),
  max(f.rang_mashiny), min(f.sila), count(*),
  -- ССЫЛКИ СЧИТАЮТСЯ ПО ТЕМ ЖЕ ФАКТАМ, ЧТО И «фактов». Здесь стоял подзапрос без условий
  -- выдачи, и счётчики считали разные множества: у Сургутнефтегаза выходило «фактов 2,
  -- ссылок 746» — потому что факта в выдаче два, а ссылки считались по всем 447 фактам
  -- предприятия, включая ушедшие в обзвон и вне парка. Владелец увидел это на экране и
  -- спросил, почему не у всех фактов есть ссылка; на деле ссылки есть у ВСЕХ фактов,
  -- врало число.
  (select count(*) from fakt_ssylka s join fakt g on g.id=s.fakt_id
    where g.inn=f.inn and g.v_parke=1 and coalesce(g.v_obzvone,0)=0
      and coalesce(g.posrednik,0)=0),
  (select group_concat(t,' | ') from (select distinct tip t from fakt x
      where x.inn=f.inn and x.v_parke=1 and x.tip<>'' order by t)),
  -- МАРКА И МОДЕЛЬ ВМЕСТЕ. Раньше сюда шла только `model`, и у 75 предприятий
  -- колонка была пустой при известном БРЕНДЕ: «Atlas Copco» без номера модели
  -- в неё не попадал. Нашлось глазами на карточке — «марки и модели: —» у
  -- предприятия с 480 фактами. Берём пару «марка модель», а если чего-то нет —
  -- то, что есть.
  (select group_concat(m,' | ') from (select distinct
        trim(coalesce(nullif(x.marka,''),'') || ' ' || coalesce(nullif(x.model,''),'')) m
      from fakt x where x.inn=f.inn and x.v_parke=1
        and (x.marka<>'' or x.model<>'') limit 8)),
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
  -- ФЛАГ ОТНОСИТСЯ К ВЫВЕДЕННОМУ НОМЕРУ, а не к предприятию. Было `max(lichnyy)` по
  -- всем контактам: строка получала метку «личный», даже если в колонке `telefon` стоял
  -- коммутатор. Замер 3-й сессии по выгрузке: 2 165 строк с меткой «личный» несли
  -- городской номер. Продавец по такой метке звонит на общий телефон и теряет заход.
  -- Теперь метка считается по ТОМУ ЖЕ номеру, что выведен в колонку.
  (select max(k.lichnyy) from kontakt k where k.inn=f.inn and k.vid='telefon'
     and k.znachenie = (select znachenie from kontakt k2 where k2.inn=f.inn
       and k2.vid='telefon' and k2.ssylok>0
       order by k2.rang, k2.lichnyy desc, k2.mobilnyy desc, k2.ssylok_pervoistochnik desc limit 1)),
  (select max(k.mobilnyy) from kontakt k where k.inn=f.inn and k.vid='telefon'
     and k.znachenie = (select znachenie from kontakt k2 where k2.inn=f.inn
       and k2.vid='telefon' and k2.ssylok>0
       order by k2.rang, k2.lichnyy desc, k2.mobilnyy desc, k2.ssylok_pervoistochnik desc limit 1)),
  (select znachenie from kontakt k where k.inn=f.inn and k.vid='email' and k.ssylok>0
     order by k.rang, k.lichnyy desc, k.ssylok_pervoistochnik desc limit 1),
  (select count(*) from kontakt k where k.inn=f.inn),
  -- ГЛАВНОЕ ДОКАЗАТЕЛЬСТВО выбираем по СИЛЕ ИСТОЧНИКА, а не только по «первоисточник».
  -- Владелец открыл карточку КАМАЗа и увидел там ссылку на ВАКАНСИЮ hh.ru — при 85
  -- ссылках, среди которых тендеры с моделями машин. Вакансия «нанимает слесаря по
  -- ремонту компрессорного оборудования» — намёк на хозяйство, а не доказательство
  -- машины. Порядок: заключение ЭПБ (машина названа с зав. номером) -> карточка
  -- закупки -> прочее -> вакансия последней.
  (select s.url from fakt_ssylka s join fakt g on g.id=s.fakt_id
     where g.inn=f.inn
     order by case when s.url like '%monitor-pb.ru/conclusion/%' then 1
                   when s.url like '%zakupki.gov.ru%common-info%' then 2
                   when s.url like '%tender.pro/api/%' or s.url like '%etpgpb%'
                        or s.url like '%tektorg%' or s.url like '%zakupki.mos.ru%' then 3
                   -- ПЕРЕЧЕНЬ — НЕ КАРТОЧКА. `monitor-pb.ru/conclusions?exploiter=ИНН`
                   -- показывает список заключений предприятия, а не конкретную запись, и
                   -- поштучно ничего не доказывает. Прежнее правило ловило его тем же
                   -- `like '%monitor-pb%'`, что и настоящее заключение, и ставило первым:
                   -- в выдаче у 364 предприятий «лучшей» стояла ссылка на перечень, хотя
                   -- у большинства из них есть конкретная карточка.
                   when s.url like '%monitor-pb.ru/conclusions%' then 6
                   when s.url like '%extendedsearch%' then 7
                   when s.url like '%hh.ru%' then 9
                   else 5 end,
              s.pervoistochnik desc, g.sila limit 1),
  ?
-- ПАРК — ЭТО ДОБОР, А НЕ ПОВТОР. Предприятия, которые уже отображаются в базе
-- обзвона «Центробежные», из парка не выдаются: продавец не должен получать одну
-- и ту же компанию дважды. Пометка `v_obzvone` ставится отдельным прогоном по
-- живому списку с сервера, факты и контакты при этом остаются на месте.
FROM fakt f WHERE f.v_parke=1 AND coalesce(f.v_obzvone,0)=0
   AND coalesce(f.posrednik,0)=0 GROUP BY f.inn""", (time.strftime('%Y-%m-%d %H:%M:%S'),))
p.commit()
cur.execute("alter table predpriyatie add column dokazano text default ''")
# ВИД НОМЕРА СЛОВАМИ. Флаг `telefon_lichnyy` у меня значит «номер привязан к НАЗВАННОМУ
# ЧЕЛОВЕКУ» (прямой рабочий тоже личный), а 3-я сессия прочла его как «мобильный» и
# насчитала 2 165 «ошибок». Определение подтверждается замером: строк «личный без имени»
# в базе НОЛЬ, а «личный + городской + с именем» — 5 709, это прямые рабочие. Флаг верен,
# врало его ИМЯ. Поэтому в выгрузке появляется колонка, которую нельзя прочесть двояко.
# ССЫЛКА НА КОНТАКТ. 3-я сессия: «ssylka_luchshaya доказывает машину, а не то, откуда
# взят номер человека; без первоисточника контакта я имею право положить строки только в
# файл "ждёт первоисточника", а не в звонок». Она права: правило владельца — каждый
# КОНТАКТ доказывается ссылкой, и в выдаче предприятий этой колонки не было вовсе,
# хотя в списке звонка она есть. Берём страницу, где видно ИМЕННО этот номер (и почту).
cur.execute("alter table predpriyatie add column ssylka_telefon text default ''")
cur.execute("alter table predpriyatie add column ssylka_pochta text default ''")
cur.execute("""update predpriyatie set ssylka_telefon = (
    select cs.source_url from contact_source cs
    where cs.inn = predpriyatie.inn and cs.znachenie = predpriyatie.telefon
      and cs.source_url like 'http%'
    order by cs.pervoistochnik desc limit 1)
  where coalesce(telefon,'')<>''""")
cur.execute("""update predpriyatie set ssylka_pochta = (
    select cs.source_url from contact_source cs
    where cs.inn = predpriyatie.inn and cs.znachenie = predpriyatie.pochta
      and cs.source_url like 'http%'
    order by cs.pervoistochnik desc limit 1)
  where coalesce(pochta,'')<>''""")
cur.execute("alter table predpriyatie add column vid_nomera text default ''")
cur.execute("""update predpriyatie set vid_nomera = case
   when coalesce(telefon,'')='' then 'номера нет'
   when mobilnyy=1 and telefon_lichnyy=1 then 'ЛИЧНЫЙ МОБИЛЬНЫЙ человека'
   when mobilnyy=1 then 'мобильный, имя не названо'
   when telefon_lichnyy=1 then 'прямой рабочий названного человека'
   else 'общий телефон предприятия' end""")
cur.execute("alter table predpriyatie add column os text default ''") if 'os' not in [
    r[1] for r in cur.execute('pragma table_info(predpriyatie)').fetchall()] else None
# правило владельца: факт без открываемой ссылки за доказанный не выдаётся.
# Здесь это видно прямо в выдаче отдельной колонкой, а не только в базе.
# ДОКАЗАНО = ЕСТЬ КОНКРЕТНАЯ КАРТОЧКА, а не «ссылка какая-нибудь».
# Прежнее правило смотрело на поле `etap` и считало доказанными всех, у кого ссылка не
# помечена поисковой. 3-я сессия посчитала по моей выгрузке: у 231 предприятия лучшая
# ссылка — ПОИСК, а не карточка. Проверил строгим определением (карточка = заключение ЭПБ,
# common-info закупки, tender.pro/api, процедура ЭТП ГПБ, тектopг, портал Москвы):
# таких предприятий 352, а помечено было 298. То есть ~54 предприятия числились
# доказанными, не имея ни одной конкретной карточки. Перекос был в ОПАСНУЮ сторону.
KARTOCHKA = ("(s.url like '%monitor-pb.ru/conclusion/%' or s.url like '%common-info%'"
             " or s.url like '%tender.pro/api/%' or s.url like '%etpgpb.ru/procedure%'"
             " or s.url like '%tektorg.ru%' or s.url like '%zakupki.mos.ru%'"
             " or s.url like '%roseltorg%' or s.url like '%fabrikant%')")
cur.execute("""update predpriyatie set dokazano = case when inn in (
    select distinct f.inn from fakt f join fakt_ssylka s on s.fakt_id=f.id
    where f.v_parke=1 and %s)
  then 'есть открываемое доказательство машины'
  else 'ДОКАЗАТЕЛЬСТВО НЕ ОТКРЫВАЕТСЯ: только поиск или перечень, конкретной карточки нет'
  end""" % KARTOCHKA)
# ВАКАНСИЯ — КОСВЕННОЕ доказательство, и это должно быть написано, а не подразумеваться.
# «Нанимает слесаря по ремонту компрессорного оборудования» говорит, что хозяйство есть,
# но машину не называет: ни модели, ни заводского номера, ни закупки. Владелец спросил
# «как понять, что это не выдуманное» — значит про такие предприятия надо говорить прямо.
cur.execute("""update predpriyatie set dokazano =
   'КОСВЕННОЕ: только вакансия (нанимают на компрессорное хозяйство), машина не названа'
   where inn in (select e.inn from predpriyatie e
     where exists(select 1 from fakt f join fakt_ssylka s on s.fakt_id=f.id
                  where f.inn=e.inn and f.v_parke=1)
       and not exists(select 1 from fakt f join fakt_ssylka s on s.fakt_id=f.id
                  where f.inn=e.inn and f.v_parke=1 and s.url not like '%hh.ru%'))""")
p.commit()
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
POLYA = ['inn','nazvanie','os','dokazano','status_egrul','region','rang_mashiny','sila_luchshaya','faktov','ssylok','tipy',
         'marki','zav_nomerov','srok_epb_istek','sostoyaniya','chelovek','dolzhnost','krug',
         'telefon','vid_nomera','ssylka_telefon',
         # ИМЯ КОЛОНКИ ВРАЛО, И ЭТО ПОЙМАЛ СОСЕД. `telefon_lichnyy` значит «номер привязан к
         # названному человеку» — прямой рабочий тоже сюда входит. Читается же оно как «личный
         # мобильный», и по нему считают: 2 238 вместо 296, в 7,6 раза шире. Числа верные,
         # врало имя. В выгрузке теперь два поля, каждое названо тем, что означает.
         'telefon_privyazan_k_cheloveku','telefon_lichnyy_mobilnyy','mobilnyy',
         'pochta','ssylka_pochta','kontaktov','vyruchka','okved',
         'ssylka_luchshaya']
cur.execute("alter table predpriyatie add column telefon_privyazan_k_cheloveku integer default 0")
cur.execute("alter table predpriyatie add column telefon_lichnyy_mobilnyy integer default 0")
cur.execute("update predpriyatie set telefon_privyazan_k_cheloveku = coalesce(telefon_lichnyy,0)")
cur.execute("""update predpriyatie set telefon_lichnyy_mobilnyy =
                 case when vid_nomera like 'ЛИЧНЫЙ МОБИЛЬНЫЙ%' then 1 else 0 end""")
p.commit()
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
