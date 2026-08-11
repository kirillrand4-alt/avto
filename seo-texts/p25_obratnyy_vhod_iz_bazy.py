# -*- coding: utf-8 -*-
"""Вход обратного хода ИЗ ЖИВОЙ БАЗЫ: все названные люди, у кого нет личного мобильного.

Прежний вход собирался из двух старых списков (251 человек 2-й сессии и 258 моих кандидатов)
— 369 целей. С тех пор база выросла, и разрыв виден числом:

    строк в единой базе                 10 033
    строк с НАЗВАННЫМ человеком          4 432
    строк с личным мобильным               517  на 155 предприятиях

То есть про четыре тысячи человек мы знаем имя, должность и предприятие, но звонить придётся
через приёмную. Обратный ход ищет номер по паре «ФИО + предприятие» — здесь обе половины есть
у каждой строки, в отличие от старых списков, где имя предприятия приходилось доставать из
`p25.db`.

КОГО НЕ БЕРУ, и каждый отказ считается:
    • у кого личный мобильный на этом же предприятии уже есть — обратный ход не добавит;
    • ФИО неполное (нет отчества и нет инициалов) — по такому запросу находятся однофамильцы;
    • пара «ИНН + ФИО» уже спрошена прежним прогоном (читаю поток `p25-obratnyy.jsonl`);
    • имя похоже на должность или на название организации, а не на человека.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ ВХОДА: в конец списка кладётся выдуманный человек «Щварцкопфер Пётр
Иванович» с настоящим предприятием. Если обратный ход вернёт ему личный номер — канал ищет
не человека, а что попало, и числам прогона верить нельзя.

Числа в КОНЦЕ.
"""
import collections
import csv
import io
import json
import os
import re

OPS = r'C:\sender\_ops'
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
# ЖУРНАЛ СПРОШЕННЫХ — ИЗ ВСЕХ ПОТОКОВ, А НЕ ИЗ ОДНОГО. Первый пересбор дал 1 988 целей,
# и число было завышено: скрипт читал только старый поток `p25-obratnyy.jsonl` и не видел
# новый `p25-obratnyy-baza.jsonl`, где уже спрошено 1 886 человек. Итог был бы не «работа»,
# а повторный опрос тех же людей за те же деньги. Список потоков теперь явный.
POTOKI = [os.path.join(OPS, 'p25-obratnyy.jsonl'),
          os.path.join(OPS, 'p25-obratnyy-baza.jsonl')]
VYHOD = os.path.join(OPS, '3s_p25_obratnyy_vhod_baza.csv')
FIO_POLNOE = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(вич|вна)$')
FIO_INICIALY = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.$')
NE_CHELOVEK = re.compile(r'общество|компани|завод|комбинат|филиал|управлени|отдел|служба|'
                         r'директор|инженер|начальник|специалист|мастер|бухгалтер', re.I)

sch = collections.Counter()
lich_u = set()          # (ИНН) у кого личный мобильный уже есть
stroki = []
with io.open(BAZA, encoding='utf-8-sig') as f:
    for r in csv.DictReader(f, delimiter=';'):
        if (r.get('vid_nomera') or '').strip().upper() == 'ЛИЧНЫЙ МОБИЛЬНЫЙ':
            lich_u.add(((r.get('inn') or '').strip(), (r.get('chelovek') or '').strip()))
        stroki.append(r)

sprosheno = set()
for POTOK in POTOKI:
    if not os.path.exists(POTOK):
        sch['НЕТ ПОТОКА: %s' % os.path.basename(POTOK)] += 1
        continue
    bylo = len(sprosheno)
    for s in io.open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        sprosheno.add((str(z.get('inn') or ''), str(z.get('fio') or '')))
    sch['спрошено по потоку %s' % os.path.basename(POTOK)] = len(sprosheno) - bylo
sch['уже спрошено прежними прогонами'] = len(sprosheno)

lyudi = {}
for r in stroki:
    inn = (r.get('inn') or '').strip()
    chel = (r.get('chelovek') or '').strip()
    if not inn or not chel:
        continue
    sch['строк с человеком'] += 1
    if (inn, chel) in lich_u:
        sch['пропуск: личный мобильный уже есть'] += 1
        continue
    if (inn, chel) in sprosheno:
        sch['пропуск: пара уже спрошена'] += 1
        continue
    if NE_CHELOVEK.search(chel):
        sch['пропуск: это не имя человека'] += 1
        continue
    if not (FIO_POLNOE.match(chel) or FIO_INICIALY.match(chel)):
        sch['пропуск: ФИО неполное — найдутся однофамильцы'] += 1
        continue
    # МОЙ ВХОД ШИРЕ, ЧЕМ ПРИЁМНИК ОБХОДА, И РАЗНИЦА СЧИТАЕТСЯ ЗДЕСЬ.
    # Прогон 11.08 показал это числом: я отдала 161 цель, а `3s_lpr_obratnyy.py` взял 23 и
    # написал «пропущено (инициалы или нет ИНН) 139». Он прав — по «Иванов И. И.» находятся
    # однофамильцы, — но моё «В ОБХОД ПОЙДЁТ 161» было завышено ровно на эти 139: я мерила
    # свой замысел, а не то, что канал реально спросит. Инициалы больше не молчат: они
    # остаются в файле (пригодятся другому каналу, где фамилии хватает), но считаются
    # отдельной строкой, и итог печатает ОБА числа.
    if not FIO_POLNOE.match(chel):
        sch['только инициалы — обход их не возьмёт, канал нужен другой'] += 1
    k = (inn, chel)
    if k in lyudi:
        sch['дубль имени внутри базы'] += 1
        continue
    lyudi[k] = {'inn': inn, 'predpriyatie': (r.get('predpriyatie') or '')[:120],
                'fio': chel, 'dolzhnost': (r.get('dolzhnost') or '')[:80],
                'otkuda': 'единая база 3-й сессии | ' + (r.get('kanaly') or '')[:60]}

spisok = list(lyudi.values())
# ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: выдуманный человек при настоящем предприятии
if spisok:
    spisok.append({'inn': spisok[0]['inn'], 'predpriyatie': spisok[0]['predpriyatie'],
                   'fio': 'Щварцкопфер Пётр Иванович', 'dolzhnost': 'главный энергетик',
                   'otkuda': 'ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ — такого человека нет'})

with io.open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda'],
                       delimiter=';')
    w.writeheader()
    w.writerows(spisok)

bez_imeni = len([z for z in spisok if not z['predpriyatie']])
print('\n\n########## ПЕРВЫЕ ВОСЕМЬ ЦЕЛЕЙ')
for z in spisok[:8]:
    print('  %-12s %-34s %-28s %s' % (z['inn'], z['predpriyatie'][:34], z['fio'][:28],
                                      z['dolzhnost'][:24]))

print('\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-52s %6d' % (k[:52], v))
s_otchestvom = len([z for z in spisok[:-1] if FIO_POLNOE.match(z['fio'])])
print('  в файл записано целей                                %6d' % (len(spisok) - 1))
print('  ИЗ НИХ ОБХОД РЕАЛЬНО СПРОСИТ (полное ФИО)            %6d' % s_otchestvom)
print('  остальные — только инициалы, ждут другого канала     %6d'
      % (len(spisok) - 1 - s_otchestvom))
print('  из них без имени предприятия (запрос будет слабее)   %6d' % bez_imeni)
print('  файл: %s' % VYHOD)
print('ИТОГ ' + json.dumps({'целей в файле': len(spisok) - 1,
                            'обход спросит': s_otchestvom,
                            'только инициалы': len(spisok) - 1 - s_otchestvom,
                            'без имени предприятия': bez_imeni}, ensure_ascii=False))
