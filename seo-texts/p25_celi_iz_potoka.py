# -*- coding: utf-8 -*-
"""Сборка списка целей для поиска людей — с заслоном «название обязано быть названием».

Зачем отдельный скрипт вместо трёх строк на месте. Три строки на месте я и написала, и они
стоили 599 человек, привязанных не к тем предприятиям:

    в потоке ЕИС два поля — `zakazchik` (имя заказчика) и `zakazchik_kartochka` (АДРЕС
    карточки организации). Я взяла второе. В список целей поехали строки вида
        7017106784;"https://zakupki.gov.ru/epz/organization/view/info.html?organizationCode=…"
    поиск честно спросил «"Иванов Иван Иванович" "https://zakupki.gov.ru/…"», получил
    страницы, где этот адрес просто упомянут, и вернул людей — ЧУЖИХ.

Ошибка не в поиске: он сделал ровно то, что просили. Ошибка в том, что никто не проверил
РЕЗУЛЬТАТ сборки целей. Поэтому здесь три заслона, и каждый называет снятое числом:

    1. в названии не должно быть «http» — это адрес, а не имя;
    2. название обязано содержать правовую форму (ООО, АО, ФГУП, ЗАВОД, УПРАВЛЕНИЕ…) —
       тот же заслон, что спас разбор имён из реестра ЕИС на четвёртом заходе;
    3. организаторы торгов (агентства и департаменты госзаказа, комитеты по закупкам)
       не владеют машиной — их в цели не берём, но и не выбрасываем: причина названа.

Запуск:
    python3 p25_celi_iz_potoka.py <выход.csv> <поток1.jsonl> [поток2.jsonl …]

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sys

VYHOD = sys.argv[1] if len(sys.argv) > 1 else 'celi.csv'
POTOKI = sys.argv[2:] or ['PARK-EIS-GLUBOKO-PODTV-3S.jsonl']
POSREDNIK = re.compile(r'агентств\w+ (государственн|муниципальн)|'
                       r'департамент\w* (государственн|муниципальн)|'
                       r'комитет\w* .{0,30}закупк|управлени\w* .{0,30}закупк|'
                       r'центр\w* .{0,20}закупок|уполномоченн\w+ орган', re.I)
FORMA = re.compile(r'\b(ООО|ОАО|ЗАО|ПАО|НАО|АО|ФГУП|ГУП|МУП|ФГБУ|ФКУ|ГБУЗ|МБУ|АК|КОМБИНАТ|'
                   r'ЗАВОД|ОБЩЕСТВО|УЧРЕЖДЕНИЕ|ПРЕДПРИЯТИЕ|КОМПАНИЯ|УПРАВЛЕНИЕ|ИНСТИТУТ|'
                   r'ФАБРИКА|ХОЛДИНГ|КОРПОРАЦИЯ)\b', re.I)
IMENA_POLEY = ('predpriyatie', 'zakazchik', 'nazvanie', 'company', 'name')

celi, snyato = {}, collections.Counter()
for p in POTOKI:
    if not os.path.exists(p):
        snyato['НЕТ ФАЙЛА: %s' % os.path.basename(p)] += 1
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(o.get('inn') or '').strip()
        if not inn.isdigit():
            snyato['ИНН пуст или не число'] += 1
            continue
        imya = ''
        for k in IMENA_POLEY:
            v = str(o.get(k) or '').strip().strip('"')
            if v and 'http' not in v:
                imya = v
                break
        if not imya:
            snyato['названия нет ни в одном поле (или везде адрес)'] += 1
            continue
        if POSREDNIK.search(imya):
            snyato['организатор торгов — машиной не владеет'] += 1
            continue
        if not FORMA.search(imya):
            snyato['на название не похоже: правовой формы нет'] += 1
            continue
        if inn not in celi:
            celi[inn] = re.sub(r'\s+', ' ', imya)[:200]

with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie\n')
    for i, z in celi.items():
        f.write('%s;"%s"\n' % (i, z.replace('"', '').replace(';', ',')))

print('\n\n########## ПЕРВЫЕ ПЯТЬ ЦЕЛЕЙ')
for i, z in list(celi.items())[:5]:
    print('  %-12s %s' % (i, z[:78]))
print('\n########## ЧИСЛА')
print('  потоков прочитано   %4d' % len(POTOKI))
print('  целей записано      %4d  -> %s' % (len(celi), VYHOD))
for k, v in snyato.most_common():
    print('     снято: %-52s %4d' % (k[:52], v))
print('ИТОГ ' + json.dumps({'целей': len(celi), 'снято': sum(snyato.values())},
                           ensure_ascii=False))
