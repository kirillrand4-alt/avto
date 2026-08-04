# -*- coding: utf-8 -*-
"""Мусорные ИМЕНА из моего канала: «Республики Карелия Латышкевич» — это не человек.

ПОВОД. Владелец показал карточку: в блоке «Люди предприятия» стоит «Республики Карелия
Латышкевич, главный механик», источник «поиск-ЛПР-3с-песочница» — мой. Разбор имени склеил
географию с фамилией: в тексте страницы стояло что-то вроде «…Республики Карелия Латышкевич
Иван Петрович…», и мой шаблон взял три слова подряд, не проверив, что первые два — не имя.

ПОЧЕМУ ЭТО ХУЖЕ, ЧЕМ ПРОСТО ОПЕЧАТКА. Такое имя нельзя ни набрать, ни спросить у секретаря, а
в карточке оно выглядит как найденный человек — то есть создаёт ложное ощущение покрытия. И
мой же обратный ход по нему будет искать несуществующего человека, тратя запросы.

Считаю по всей базе: сколько имён содержат слова, которых в ФИО быть не может.
"""
import collections
import json
import re
import sqlite3

NE_IMYA = re.compile(
    r'\b(?:республик\w*|област\w*|кра[йя]|город\w*|район\w*|округ\w*|федерац\w*|'
    r'министерств\w*|управлени\w*|филиал\w*|общество|акционерн\w*|ограниченн\w*|'
    r'предприяти\w*|учреждени\w*|компани\w*|завод\w*|комбинат\w*|фабрик\w*|'
    r'ООО|ОАО|ЗАО|ПАО|АО|ГУП|МУП|ФГУП|ИНН|ОГРН)\b', re.I)
DOLZHNOST_V_IMENI = re.compile(
    r'\b(?:директор|инженер|механик|энергетик|начальник|заместител\w*|главн\w*|'
    r'руководител\w*|специалист|мастер)\b', re.I)

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
sch = collections.Counter()
primery = collections.defaultdict(list)
for inn, person, src in cx.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(source,'') from person"):
    p = (person or '').strip()
    if not p:
        continue
    bad = []
    if NE_IMYA.search(p):
        bad.append('география или юрлицо в имени')
    if DOLZHNOST_V_IMENI.search(p):
        bad.append('должность внутри имени')
    if len(p.split()) > 4:
        bad.append('больше четырёх слов')
    if re.search(r'\d', p):
        bad.append('цифры в имени')
    if not bad:
        continue
    kanal = src.split(';')[0].strip()[:40] or '(пусто)'
    for b in bad:
        sch[f'{b} | {kanal}'] += 1
        if len(primery[b]) < 4:
            primery[b].append({'inn': inn, 'imya': p[:70], 'istochnik': kanal})
o = {'мусорных_имён_по_видам_и_каналам': dict(sch.most_common(14)), 'примеры': dict(primery)}
o['всего_людей'] = cx.execute('select count(*) from person').fetchone()[0]
print(json.dumps(o, ensure_ascii=False, indent=1)[:3500])
