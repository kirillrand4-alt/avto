# -*- coding: utf-8 -*-
"""Проверяет «точную» базу 3-й сессии СВОИМ прибором, прежде чем вливать.

Владелец: «если там реально теперь только доказанные телефоны — влей и убери не доказанные».
Ключевое слово — «реально»: её слово о своей работе я не пересказываю, а перемеряю. Она
объявила четыре условия отбора, и здесь каждое проверяется отдельно, на её же файле:

    1. ссылка есть и это http, а не пересказ;
    2. личный мобильный — цитата содержит И номер, И фамилию человека;
    3. источник не агрегатор (prodoctorov, vk, careerist — там карточку заводит не
       предприятие, и полный тёзка неотличим; это ровно тот дефект, на котором меня поймал
       владелец снимком неонатолога);
    4. у номера предприятия назван человек, у почты — не общая.

Плюс два условия от себя, которых в её описи нет:

    5. номер записан СВЯЗНО, а не собран из соседних чисел («8 (41136) 99-000 доб.4-78-59»
       склеивается в мнимый мобильный 79900047859 — на этом я уже обжигался на АЛРОСА);
    6. предприятие есть в моей выдаче (иначе контакт некуда класть).

Итог печатается по каждому условию отдельно: сколько строк прошло, сколько нет и с чем
именно. Вливать — отдельным прибором и только то, что прошло всё.

Запуск: python3 park_1s_proverit_tochno_3s.py [--vsyo]
"""
import csv
import os
import re
import sqlite3
import sys
from urllib.parse import urlparse

D = os.path.dirname(os.path.abspath(__file__))
FAYL = os.path.join(D, 'PARK-BAZA-TOCHNO-3S.csv')
AGREGATORY = ('prodoctorov', 'vk.com', 'ok.ru', 'facebook', 'instagram', 'avito', 'youla',
              'hh.ru', 'superjob', 'zoon.', 'yell.', '2gis', 'flamp', 'orgpage', 'rusprofile',
              'list-org', 'checko', 'careerist', 'vseinstrumenti')
OBSHCHIE = ('info@', 'office@', 'mail@', 'zakupki@', 'tender@', 'secretar', 'priemn', 'post@',
            'sekretar', 'general@', 'company@', 'contact@', 'reception')
csv.field_size_limit(10 ** 7)


def cifry(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    return c if len(c) == 10 else ''


def svyazno(nomer10, tekst):
    """Номер записан как ТЕЛЕФОН, а не собран из соседних чисел."""
    return bool(re.search(r'[\s\-()+]{0,3}'.join(nomer10), tekst or ''))


def familii(chelovek):
    return [w for w in re.findall(r'[А-ЯЁ][а-яё]{2,}', chelovek or '')]


p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c = p.cursor()
vydacha = {r[0] for r in c.execute("""select distinct inn from fakt where v_parke=1
             and coalesce(v_obzvone,0)=0 and coalesce(posrednik,0)=0""")}

schet = {'строк всего': 0, 'предприятий': set(), 'ЛИЧНЫХ МОБИЛЬНЫХ': 0,
         'городских': 0, 'почт': 0, 'имя без номера': 0}
bracket = {'1. нет http-ссылки': [], '2. личный мобильный без номера в цитате': [],
           '2. личный мобильный без фамилии в цитате': [], '3. источник — агрегатор': [],
           '4. номер без человека': [], '4. почта общая': [],
           '5. номер собран из соседних чисел': [], '6. предприятия нет в моей выдаче': []}
proshli = 0
for r in csv.DictReader(open(FAYL, encoding='utf-8-sig'), delimiter=';'):
    schet['строк всего'] += 1
    inn = (r.get('inn') or '').strip()
    schet['предприятий'].add(inn)
    nomer = cifry(r.get('nomer'))
    pochta = (r.get('pochta') or '').strip().lower()
    vid = (r.get('vid_nomera') or '').strip()
    chel = (r.get('chelovek') or '').strip()
    citata = r.get('citata') or ''
    ssylki = [u.strip() for u in (r.get('istochniki') or '').split('|') if u.strip()]
    http = [u for u in ssylki if u.startswith('http')]
    if vid.upper().startswith('ЛИЧНЫЙ'):
        schet['ЛИЧНЫХ МОБИЛЬНЫХ'] += 1
    elif nomer:
        schet['городских'] += 1
    elif pochta:
        schet['почт'] += 1
    else:
        schet['имя без номера'] += 1

    beda = []
    if not http:
        beda.append('1. нет http-ссылки')
    if vid.upper().startswith('ЛИЧНЫЙ'):
        if not (nomer and svyazno(nomer[-10:], citata)):
            beda.append('2. личный мобильный без номера в цитате')
        elif not any(f in citata for f in familii(chel)):
            beda.append('2. личный мобильный без фамилии в цитате')
    domeny = {(urlparse(u).netloc or '').replace('www.', '').lower() for u in http}
    if domeny and all(any(a in d for a in AGREGATORY) for d in domeny):
        beda.append('3. источник — агрегатор')
    if nomer and not chel:
        beda.append('4. номер без человека')
    if pochta and not nomer and any(o in pochta for o in OBSHCHIE):
        beda.append('4. почта общая')
    if nomer and citata and not svyazno(nomer[-10:], citata):
        beda.append('5. номер собран из соседних чисел')
    if inn not in vydacha:
        beda.append('6. предприятия нет в моей выдаче')

    if beda:
        for b in beda:
            bracket[b].append((inn, chel[:26], nomer or pochta, (http[0] if http else '')[:52]))
    else:
        proshli += 1

print('ПРОВЕРКА PARK-BAZA-TOCHNO-3S.csv своим прибором')
print()
print('  строк всего .............. %d' % schet['строк всего'])
print('  предприятий .............. %d' % len(schet['предприятий']))
print('  ЛИЧНЫХ МОБИЛЬНЫХ ......... %d' % schet['ЛИЧНЫХ МОБИЛЬНЫХ'])
print('  городских ................ %d' % schet['городских'])
print('  почт ..................... %d' % schet['почт'])
print('  имя без номера ........... %d' % schet['имя без номера'])
print()
print('  ПРОШЛИ ВСЕ ШЕСТЬ УСЛОВИЙ . %d (%.1f%%)'
      % (proshli, 100.0 * proshli / max(1, schet['строк всего'])))
print()
print('не прошли, по условиям:')
for k in sorted(bracket):
    if bracket[k]:
        print('  %-46s %d' % (k, len(bracket[k])))
skolko = 6 if '--vsyo' not in sys.argv else 40
for k in sorted(bracket):
    if not bracket[k]:
        continue
    print()
    print('%s — примеры:' % k)
    for inn, chel, zn, u in bracket[k][:skolko]:
        print('   %-11s %-26s %-16s %s' % (inn, chel, zn, u))
p.close()
