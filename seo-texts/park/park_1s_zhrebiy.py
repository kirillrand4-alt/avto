# -*- coding: utf-8 -*-
"""Жребий для проверки доказанности — ПО ФАКТАМ, а не по ссылкам.

Дефект прежнего жребия. Я брал случайную строку из `fakt_ssylka` и спрашивал: доказывает ли
она? Но доказанность — свойство ФАКТА, а не строки: у факта бывает пять ссылок, и достаточно
одной сильной. Жребий по строкам меряет другое — долю сильных строк, и она тем ниже, чем
больше у нас накоплено дополнительных адресов. В замере 10.08 20:34 это видно прямо: из 13
открывшихся 6 «машина есть, ИНН нет» и 3 «ИНН есть, машины нет» — но у половины этих фактов
рядом лежит вторая ссылка, закрывающая недостающее.

Теперь: выбираем случайный ФАКТ выдачи, а к нему — ЛУЧШУЮ его ссылку по тому же порядку
качества, что и в отборе на съёмку (ЭПБ карточка -> 223-ФЗ -> 44-ФЗ -> прочее; ЭТП ГПБ,
перечень и вакансия — в самый конец, они не доказывают ИНН). Так замер отвечает на вопрос
владельца «как понять, что это не выдуманное», а не на вопрос о качестве нашей архивной
привычки хранить все адреса.

Запуск: python3 park_1s_zhrebiy.py <зерно> [сколько]
"""
import json, os, random, sqlite3, sys

D = os.path.dirname(os.path.abspath(__file__))
zerno = int(sys.argv[1]) if len(sys.argv) > 1 else 1
skolko = int(sys.argv[2]) if len(sys.argv) > 2 else 20
random.seed(zerno)
c = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)
fakty = c.execute("""select f.id, f.inn, f.tip, coalesce(f.model,''), coalesce(f.marka,''),
                            f.vid_fakta
                       from fakt f
                      where f.v_parke=1 and coalesce(f.v_obzvone,0)=0
                        and coalesce(f.posrednik,0)=0
                        and exists(select 1 from fakt_ssylka s
                                    where s.fakt_id=f.id and s.url like 'http%')""").fetchall()
print('фактов выдачи со ссылкой: %d' % len(fakty))
vyb = random.sample(fakty, min(skolko, len(fakty)))
zad = []
for fid, inn, tip, model, marka, vid in vyb:
    url = c.execute("""select url from fakt_ssylka where fakt_id=? and url like 'http%'
                        order by case
                          when url like '%monitor-pb.ru/conclusion/%' then 1
                          when url like '%/223/purchase%' then 2
                          when url like '%notice/ea44%' then 3
                          when url like '%mos.ru%' or url like '%tektorg%' then 4
                          when url like '%tender.pro/api%' then 5
                          when url like '%etpgpb.ru%' then 7
                          when url like '%conclusions?exploiter=%' then 8
                          when url like '%extendedsearch%' then 9
                          when url like '%hh.ru%' then 9
                          else 6 end, length(url) limit 1""", (fid,)).fetchone()[0]
    zad.append({'inn': inn, 'tip': tip, 'model': model or marka, 'url': url, 'vid': vid})
with open(os.path.join(D, '_5ssylok.json'), 'w', encoding='utf-8') as f:
    json.dump(zad, f, ensure_ascii=False, indent=1)
import collections
print('жребий %d фактов, зерно %d' % (len(zad), zerno))
print('лучшие ссылки по доменам:', dict(collections.Counter(z['url'].split('/')[2] for z in zad)))
c.close()
