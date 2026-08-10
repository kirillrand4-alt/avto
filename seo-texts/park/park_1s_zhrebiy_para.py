# -*- coding: utf-8 -*-
"""Жребий ПАРАМИ: у факта берётся ссылка на машину И ссылка на ИНН, проверяются обе.

Прежний жребий брал ОДНУ лучшую ссылку и спрашивал, доказывает ли она всё сразу. Это давало
54 % — и наказывало за то, что доказательство честно разнесено на две страницы: извещение
44-ФЗ печатает название заказчика без ИНН, а ИНН лежит на карточке организации. Мерка по паре
даёт 63 % фактов, и она отвечает правилу владельца «ссылок несколько — строк несколько».

Чтобы не было двух чисел про одно и то же, жребий переводится на ту же мерку: берём факт,
берём ЛУЧШУЮ ссылку каждого рода и проверяем обе.

    ссылка на машину  — карточка ЭПБ, 223-ФЗ, 44-ФЗ, mos.ru, tektorg, tender.pro, ЭТП ГПБ
    ссылка на ИНН     — карточка ЭПБ, 223-ФЗ (там ИНН печатают), карточка организации ЕИС

У ЭПБ и 223-ФЗ одна страница закрывает оба рода — тогда пара вырождается в одну ссылку, и это
честно: проверяется то, что есть.

Запуск: python3 park_1s_zhrebiy_para.py <зерно> [сколько]
"""
import json, os, random, sqlite3, sys

D = os.path.dirname(os.path.abspath(__file__))
zerno = int(sys.argv[1]) if len(sys.argv) > 1 else 1
skolko = int(sys.argv[2]) if len(sys.argv) > 2 else 20
random.seed(zerno)
c = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park.db'), uri=True)

MASH = """order by case
    when url like '%monitor-pb.ru/conclusion/%' then 1
    when url like '%/223/purchase%' then 2
    when url like '%notice/ea44%' then 3
    when url like '%mos.ru%' or url like '%tektorg%' then 4
    when url like '%tender.pro/api%' then 5
    when url like '%etpgpb.ru%' then 6
    else 9 end, length(url) limit 1"""
INNS = """order by case
    when url like '%monitor-pb.ru/conclusion/%' then 1
    when url like '%/223/purchase%' then 2
    when url like '%epz/organization/%' then 3
    else 9 end, length(url) limit 1"""

fakty = c.execute("""select f.id, f.inn, f.tip, coalesce(f.model,''), coalesce(f.marka,'')
                       from fakt f
                      where f.v_parke=1 and coalesce(f.v_obzvone,0)=0
                        and coalesce(f.posrednik,0)=0
                        and exists(select 1 from fakt_ssylka s
                                    where s.fakt_id=f.id and s.url like 'http%')""").fetchall()
vyb = random.sample(fakty, min(skolko, len(fakty)))
zad = []
for fid, inn, tip, model, marka in vyb:
    m = c.execute("select url from fakt_ssylka where fakt_id=? and url like 'http%' " + MASH,
                  (fid,)).fetchone()
    i = c.execute("""select url from fakt_ssylka where fakt_id=? and url like 'http%'
                      and (url like '%monitor-pb.ru/conclusion/%' or url like '%/223/purchase%'
                           or url like '%epz/organization/%') """ + INNS, (fid,)).fetchone()
    zad.append({'fakt_id': fid, 'inn': inn, 'tip': tip, 'model': model or marka,
                'url_mashina': m[0] if m else '', 'url_inn': i[0] if i else ''})
with open(os.path.join(D, '_zhrebiy_para.json'), 'w', encoding='utf-8') as f:
    json.dump(zad, f, ensure_ascii=False, indent=1)
est_para = sum(1 for z in zad if z['url_inn'])
odna = sum(1 for z in zad if z['url_inn'] and z['url_inn'] == z['url_mashina'])
print('жребий %d фактов, зерно %d' % (len(zad), zerno))
print('  есть ссылка на ИНН ................ %d' % est_para)
print('  из них та же страница, что машина . %d' % odna)
print('  ссылки на ИНН нет вовсе ........... %d' % (len(zad) - est_para))
c.close()
