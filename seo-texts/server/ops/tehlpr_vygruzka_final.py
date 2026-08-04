# -*- coding: utf-8 -*-
"""Выгрузка «технарь + личный мобильный» с честным разделением по силе должности.

ТРИ СОРТА, И СМЕШИВАТЬ ИХ НЕЛЬЗЯ
  A  должность с предприятия     «главный механик», «инженер-энергетик» —
                                 человек так называется на работе;
  B  роль из карточки закупки    «контактное лицо по техническим вопросам» —
                                 так его назвала процедура; кем работает,
                                 отсюда неизвестно;
  C  отсеяно                     «инженер отдела продаж» и подобное: слово
                                 «инженер» есть, отношения к технической
                                 службе нет.

Числа печатаю ПОСЛЕДНИМИ: хвост вывода обрезается, и сводка, стоящая первой,
до меня не доезжает — уже дважды сегодня.
"""
import csv, io, os, re, sys
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

ВЫХОД = r'C:\seostat\drop\drop-storage\TEHLPR-MOBILNYY-1S.csv'
ТЕХ = ('инженер', 'механик', 'энергетик', 'технич', 'производств', 'кипиа',
       'метролог', 'технолог', 'главный сварщик', 'главный метролог')
НЕ_ТЕХ = re.compile(r'отдела продаж|по продажам|по сбыту|менеджер по прод|'
                    r'коммерческ|отдел маркетинга|преподавател|заведующ\w* отделением|'
                    r'колледж|техникум', re.I)
ИЗ_ЗАПРОСА = re.compile(r'контактн\w* лиц|консультаци|по вопросам|'
                        r'ответственн\w* за процедур|для уточнения|контакт по', re.I)

db = EDB.EnrichDB()
c = Counter()
A, B = [], []
for инн, чел, пост, роль, тел, не_личный, урл, ист in db.cx.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(post,''), COALESCE(role,''), "
        "COALESCE(phone,''), COALESCE(nomer_ne_lichnyy,''), COALESCE(source_url,''), "
        "COALESCE(source,'') FROM people WHERE COALESCE(phone,'')<>''"):
    инн, чел, пост, роль = str(инн), str(чел), str(пост), str(роль)
    подпись = f'{пост} {роль}'.casefold()
    if not any(т in подпись for т in ТЕХ):
        continue
    ц = ''.join(x for x in str(тел) if x.isdigit())[-10:]
    if not (len(ц) == 10 and ц[0] == '9'):
        c['технарь, но номер городской'] += 1
        continue
    if не_личный:
        c['мобильный, но помечен как не личный'] += 1
        continue
    if НЕ_ТЕХ.search(подпись):
        c['C отсеяно: слово техническое, служба — нет'] += 1
        continue
    строка = {'inn': инн, 'chelovek': чел, 'dolzhnost': пост,
              'telefon': str(тел), 'istochnik': str(ист),
              'ssylka': str(урл)}
    if ИЗ_ЗАПРОСА.search(пост):
        c['B роль из карточки закупки'] += 1
        строка['sort'] = 'B: роль из карточки закупки, должность неизвестна'
        B.append(строка)
    else:
        c['A должность с предприятия'] += 1
        строка['sort'] = 'A: должность названа предприятием'
        A.append(строка)

поля = ['sort', 'inn', 'chelovek', 'dolzhnost', 'telefon', 'istochnik', 'ssylka']
with io.open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
    п = csv.DictWriter(ф, fieldnames=поля, delimiter=';')
    п.writeheader()
    п.writerows(A + B)
    ф.flush(); os.fsync(ф.fileno())

print('ПРИМЕРЫ СОРТА A (должность с предприятия):')
for з in A[:10]:
    print(f"   {з['inn']:12} {з['chelovek'][:24]:24} {з['dolzhnost'][:30]:30} {з['telefon'][:17]}")
print()
print('=== ЧИСЛА ===')
for к, v in sorted(c.items()):
    print(f'   {к:48} {v:5}')
print(f'   {"предприятий в сорте A":48} {len({з["inn"] for з in A}):5}')
print(f'   {"предприятий в сорте B":48} {len({з["inn"] for з in B}):5}')
print(f'   файл: {os.path.basename(ВЫХОД)}, строк {len(A) + len(B)}')
