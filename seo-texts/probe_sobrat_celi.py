# -*- coding: utf-8 -*-
"""Собрать вход обратного хода: у файла 1-й сессии нет НАЗВАНИЯ предприятия, а запрос без него слеп.

Их файл — inn, chelovek, dolzhnost, rol, ssylka. Запрос обратного хода строится как
«"Фамилия Имя Отчество" "<название предприятия>"», и без названия он находит однофамильцев по
всей стране. Название беру из панели по ИНН — оно там есть у всех.

Заодно переименовываю колонку: у них человек называется `chelovek`, мой разбор ждёт `fio`.
Молча это не сработало: прогон честно сказал «полных ФИО 0, пропущено 219» — и это тот редкий
случай, когда чужое имя поля видно сразу, потому что счётчик пропусков равен числу строк.
"""
import csv
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
# Имя колонки берётся из схемы, а не угадывается: `company` в таблице company нет.
kol = [r[1] for r in cx.execute('pragma table_info(company)')]
pole = next((k for k in ('predpriyatie', 'title', 'name', 'nazvanie') if k in kol), None)
if not pole:
    print('колонки company:', kol)
    raise SystemExit('поля с названием предприятия нет — не угадываю')
imena = dict(cx.execute(f'select inn, coalesce("{pole}",\'\') from company'))
print('название берётся из колонки', pole)

vhod = list(csv.DictReader(open(r'C:\sender\_ops\3s_CELI-obratnogo-hoda-prioritet.csv',
                               encoding='utf-8-sig'), delimiter=';'))
out, bez_imeni = [], 0
for r in vhod:
    inn = (r.get('inn') or '').strip()
    fio = (r.get('chelovek') or r.get('fio') or '').strip()
    nazv = imena.get(inn, '')
    if not nazv:
        bez_imeni += 1
        continue
    out.append({'inn': inn, 'fio': fio, 'dolzhnost': r.get('dolzhnost') or r.get('rol') or '',
                'predpriyatie': nazv})
put = r'C:\sender\_ops\3s_CELI-gotovye.csv'
with open(put, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['inn', 'fio', 'dolzhnost', 'predpriyatie'], delimiter=';')
    w.writeheader()
    w.writerows(out)
polnyh = sum(1 for r in out if len(r['fio'].split()) >= 3 and re.search(
    r'(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична|инична)\b', r['fio']))
print(f'вход {len(vhod)} строк | без названия предприятия {bez_imeni} | записано {len(out)} '
      f'| из них полных ФИО {polnyh} → {put}')
