# -*- coding: utf-8 -*-
"""Новое задание на съёмку доказательств: круг закончен, ставим следующий.

Первое задание (4 901 факт) сервер отснял до конца: в базе 4 694 снимка, ИНН виден на 3 818,
машина названа на 4 555. Теперь берём тех, у кого снимка ещё нет.

Порядок отбора — по пользе для продавца, а не по порядку в базе:
  1. предприятия выдачи, у которых НЕТ НИ ОДНОГО снимка (сначала укрываем всех хотя бы одним
     доказательством, потом углубляем);
  2. внутри предприятия — самый сильный факт: карточка ЭПБ (ИНН виден в 100 % снимков),
     затем карточка 223-ФЗ (99 %), затем 44-ФЗ (78 %);
  3. ЭТП ГПБ не берём вовсе: 250 снятых страниц, ИНН не виден НИ НА ОДНОЙ — снимок там
     ничего не добавит к тому, что уже известно.
"""
import json, os, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
c = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
rows = c.execute("""
    select f.inn, f.id, s.url, f.tip, coalesce(f.nazvanie,''),
           case when s.url like '%monitor-pb.ru/conclusion/%' then 1
                when s.url like '%/223/purchase%' then 2
                when s.url like '%notice/ea44%' then 3
                else 5 end kach,
           (select count(*) from dokaz_snimok d2 join fakt f2 on f2.id=d2.fakt_id
             where f2.inn=f.inn) est_u_inn
      from fakt f
      join fakt_ssylka s on s.fakt_id = f.id
     where f.v_parke=1 and coalesce(f.v_obzvone,0)=0 and coalesce(f.posrednik,0)=0
       and f.id not in (select fakt_id from dokaz_snimok)
       and s.url like 'http%'
       and s.url not like '%etpgpb.ru%'
       and s.url not like '%conclusions?exploiter=%'
       and s.url not like '%hh.ru%'
     order by est_u_inn, kach, f.inn
""").fetchall()

zad, vidno = [], {}
for inn, fid, url, tip, imya, kach, est in rows:
    n = vidno.get(inn, 0)
    if n >= 2:          # два снимка на предприятие: машина и подтверждение, дальше не льём
        continue
    vidno[inn] = n + 1
    zad.append({'inn': inn, 'fakt_id': fid, 'url': url, 'tip': tip, 'nazvanie': imya[:120]})

with open(os.path.join(D, '_dokaz_zadanie.json'), 'w', encoding='utf-8') as f:
    json.dump(zad, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
bez = sum(1 for inn in vidno if not c.execute(
    """select count(*) from dokaz_snimok d join fakt f on f.id=d.fakt_id where f.inn=?""",
    (inn,)).fetchone()[0])
print('фактов-кандидатов без снимка ..... %d' % len(rows))
print('в задание отобрано ............... %d' % len(zad))
print('  предприятий в задании .......... %d' % len(vidno))
print('  из них НИ ОДНОГО снимка сейчас . %d' % bez)
c.close()
