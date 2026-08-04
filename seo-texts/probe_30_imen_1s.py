# -*- coding: utf-8 -*-
"""Собрать 30 технических имён 1-й сессии для сверки приёмов.

Их просьба дословно: «прогоните 30 моих имён своим приёмом. У меня 1,3 % телефонов, у вас 32 %
— если разница в приёме, отдам вам все 384 и уйду в панель». Беру их людей из enrich.db
(source LIKE '%поиск-ЛПР%'), только технических и только с полным ФИО — на инициалах мой приём
не работает по устройству, и сравнивать надо сравнимое.
"""
import csv
import re
import sqlite3

cx = sqlite3.connect(r'C:\sender\enrich.db')
kol = [r[1] for r in cx.execute('pragma table_info(people)')]
print('колонки people:', kol)
pole_imya = next((k for k in ('person', 'fio', 'name') if k in kol), None)
pole_post = next((k for k in ('post', 'position', 'dolzhnost') if k in kol), None)
pole_src = next((k for k in ('source', 'src') if k in kol), None)
rows = cx.execute(
    f'select inn, coalesce("{pole_imya}",\'\'), coalesce("{pole_post}",\'\') from people '
    f'where "{pole_src}" like \'%поиск-ЛПР%\'').fetchall()
print('строк поиска ЛПР:', len(rows))

TEH = re.compile(r'главн\w+\s+(?:инженер|энергетик|механик)|технич\w+\s+директор|'
                 r'директор\w*\s+по\s+производ|начальник\s+(?:цех|производ|ОГЭ|ОГМ)', re.I)
POLNOE = re.compile(r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)\b')
imena = {}
for inn, imya, post in rows:
    if not TEH.search(post or '') or not POLNOE.search(imya or ''):
        continue
    if len((imya or '').split()) < 3:
        continue
    imena.setdefault((inn, imya), post)
print('технических с полным ФИО:', len(imena))

# Название предприятия — из панели.
pn = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
nazv = dict(pn.execute("select inn, coalesce(predpriyatie,'') from company"))
out = []
for (inn, imya), post in list(imena.items()):
    if nazv.get(inn):
        out.append({'inn': inn, 'fio': imya, 'dolzhnost': post,
                    'predpriyatie': nazv[inn]})
    if len(out) >= 30:
        break
put = r'C:\sender\_ops\3s_30-imen-1s.csv'
with open(put, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['inn', 'fio', 'dolzhnost', 'predpriyatie'], delimiter=';')
    w.writeheader()
    w.writerows(out)
print(f'записано {len(out)} → {put}')
for z in out[:5]:
    print(' ', z['inn'], z['fio'], '|', z['dolzhnost'][:40])
