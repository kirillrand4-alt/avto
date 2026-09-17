# -*- coding: utf-8 -*-
"""Эксель по словам ПРОИЗВОДСТВА: предприятия, которым компрессор нужен, но не назван.

Откуда взялся этот заход. Портфельный провалился: 9 467 карточек дали 17 объектов нашей
темы. Зато внутри него нашлись 372 карточки, где стоит производственное слово - окраска,
литьё, прокат, термичка, метанол, - и компрессор таким объектам нужен физически, хотя
слова «компрессор» в названии нет. Здесь те же слова взяты по ВСЕМУ реестру.

Слов 123, все с ненулевой отдачей, включая заведомо шумные («молоч» 1 387, «кирпичн» 673):
правило владельца - берём всё, сортируем потом. Шум ушёл в свой лист с причиной.

Два разных признака, и путать их нельзя:
  ОТРАСЛЬ - по слову, которым запись найдена. Слов может быть несколько, тогда и отрасль
            составная: «пищевая + химия» честнее, чем выбранная одна.
  КЛАСС   - это вообще производственный объект или слово поймало ремонт крыши.
"""
import collections
import csv
import io
import json
import os
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

KAT = os.path.dirname(os.path.abspath(__file__))
VYHOD = os.path.join(KAT, 'EGRZ-PROIZVODSTVA.xlsx')
SHRIFT = 'Arial'
TEH = re.compile(r'инженер|энергетик|механик|технолог|техдирект|техн|производств|цех|'
                 r'КИПиА|АСУ|снабжен|закупк|заказчик|капитальн|проект|эксплуатац', re.I)

s = [json.loads(l) for l in io.open(os.path.join(KAT, 'PROIZVODSTVA-RAZOBRANO.jsonl'),
                                    encoding='utf-8')]
nov = {r['inn']: r['novoe_dlya_bazy'] for r in csv.DictReader(
    io.open(os.path.join(KAT, '3s_PROIZV-NOVIZNA.csv'), encoding='utf-8-sig'), delimiter=';')}
kont = list(csv.DictReader(io.open(os.path.join(KAT, '3s_PROIZV-KONTAKTY.csv'),
                                   encoding='utf-8-sig'), delimiter=';'))
povod = list(csv.DictReader(io.open(os.path.join(KAT, '3s_PROIZV-POVODY.csv'),
                                    encoding='utf-8-sig'), delimiter=';'))
for k in kont:
    k['tehnicheskaya'] = 'да' if TEH.search((k.get('chelovek_dolzhnost') or '') + ' '
                                            + (k.get('rol_kanon') or '')) else ''
po_tel, po_teh, po_pov = collections.Counter(), collections.Counter(), collections.Counter()
for k in kont:
    if (k.get('telefon') or '').strip():
        po_tel[k['inn']] += 1
    if k['tehnicheskaya']:
        po_teh[k['inn']] += 1
for p in povod:
    po_pov[p['inn']] += 1

PROM = sorted([x for x in s if x['klass'] == 'ПРОИЗВОДСТВО'],
              key=lambda z: z.get('data') or '', reverse=True)
SOMN = sorted([x for x in s if x['klass'] == 'сомнительно'],
              key=lambda z: z.get('data') or '', reverse=True)
OTSEV = sorted([x for x in s if x['klass'].startswith('отсеяно')],
               key=lambda z: z.get('data') or '', reverse=True)
PRIOR = [x for x in PROM if x['prioritetnaya']]
print('производство %d · приоритетных %d · сомнительно %d · отсеяно %d'
      % (len(PROM), len(PRIOR), len(SOMN), len(OTSEV)))

zi = {x['zastroyshchik_inn'] for x in PROM if x.get('zastroyshchik_inn')}
pi = {x['proektirovshchik_inn'] for x in PROM if x.get('proektirovshchik_inn')}
zp = {x['zastroyshchik_inn'] for x in PRIOR if x.get('zastroyshchik_inn')}

wb = Workbook()
ZAG = Font(name=SHRIFT, size=12, bold=True)
OB = Font(name=SHRIFT, size=10)
ws = wb.active
ws.title = 'Как читать'
OPIS = [
    ('Предприятия, которым компрессор нужен, но в названии проекта он не назван', True),
    ('', False),
    ('ЗАЧЕМ ЭТОТ ФАЙЛ. Поиск по слову «компрессор» находит только тех, кто назвал машину в', False),
    ('   имени объекта. «Строительство цеха гальванических покрытий», «Литейный цех»,', False),
    ('   «Цех окраски» компрессор не называют - а без сжатого воздуха ни один из них не', False),
    ('   работает. Здесь 123 слова производства прогнаны по ВСЕМУ реестру ЕГРЗ.', False),
    ('', False),
    ('ЧИСЛА', True),
    ('   выгружено карточек ...................... %d' % len(s), False),
    ('   из них НОВЫХ, которых у нас не было ..... %d'
     % len([x for x in s if x['novaya_kartochka'] == 'да']), False),
    ('   признано ПРОИЗВОДСТВОМ .................. %d  (лист «Производство»)' % len(PROM), False),
    ('   из них в 7 приоритетных отраслях ........ %d' % len(PRIOR), False),
    ('', False),
    ('   разных предприятий-застройщиков ......... %d, из них НОВЫХ для базы %d'
     % (len(zi), len([i for i in zi if nov.get(i) == 'да'])), False),
    ('   из них в приоритетных отраслях .......... %d, из них НОВЫХ %d'
     % (len(zp), len([i for i in zp if nov.get(i) == 'да'])), False),
    ('   разных проектировщиков .................. %d, из них НОВЫХ %d'
     % (len(pi), len([i for i in pi if nov.get(i) == 'да'])), False),
    ('', False),
    ('   Для сравнения: вся прошлая работа по слову «компрессор» и его родне дала', False),
    ('   154 застройщика и 175 проектировщиков. Здесь их на порядок больше.', False),
    ('', False),
    ('ЧТО ЭТО ЗА ПРЕДПРИЯТИЯ, а не просто ИНН', True),
    ('   пищевая 1 594 карточки · металлургия и горное 639 · машиностроение 559 ·', False),
    ('   химия и нефтехимия 380 · ЦБП и деревообработка 265 · фармацевтика 160 ·', False),
    ('   лёгкая 105 · цементная 83 · стекольная 30 · энергетика 12.', False),
    ('   Отрасль ставится по слову, которым запись найдена. Если слов несколько, отрасль', False),
    ('   составная - «пищевая + химия и нефтехимия». Это честнее, чем выбрать одну.', False),
    ('', False),
    ('ЛИСТЫ', True),
    ('   «Производство»  %5d карточек. Колонка «Найден по слову» говорит, ЧТО сработало.' % len(PROM), False),
    ('   «Приоритетные»  %5d карточек - те же, но только семь отраслей владельца.' % len(PRIOR), False),
    ('   «Предприятия»   %5d застройщиков: отрасль, число объектов, телефоны, новизна.' % len(zi), False),
    ('   «Сомнительно»   %5d карточек: слово есть, а признака завода или цеха в названии' % len(SOMN), False),
    ('                        нет. Не мусор и не находка - смотреть глазами.', False),
    ('   «Отсеяно»       %5d карточек, у каждой написано, почему.' % len(OTSEV), False),
    ('   «Контакты»      %5d строк из нашей базы · «Поводы» %d строк.' % (len(kont), len(povod)), False),
    ('', False),
    ('ПОЧЕМУ ОТСЕЯНО - классы названы по живым образцам', True),
    ('   жильё и благоустройство  1 060 - «капремонт кровли кирпичного дома», «дворовая', False),
    ('                            территория». Слово «кирпичн» дало 673 записи, и почти', False),
    ('                            все такие.', False),
    ('   инженерные сети            482 - водопровод, канализация, газопровод, кабельные', False),
    ('                            линии. Сюда же «внеплощадочн» - сети к жилым кварталам.', False),
    ('   дорога и линейный объект   313 - «ул. Кожевенная», «пер. Кирпичный»: слово', False),
    ('                            производства оказалось названием улицы.', False),
    ('   соцобъект                  152 - школы, больницы, спортивные объекты.', False),
    ('', False),
    ('ЧЕГО В ФАЙЛЕ НЕТ, сказано прямо:', True),
    ('   • компрессора в этих проектах никто не обещал. Признак косвенный: так работает', False),
    ('     производство, а не так написано в документе. Это гипотеза с адресом и ИНН,', False),
    ('     а не подтверждённая потребность.', False),
    ('   • контакты есть только у %d ИНН из %d - остальных надо добывать.'
     % (len({k['inn'] for k in kont}), len(nov)), False),
    ('   • людей в ЕГРЗ нет вовсе. Телефоны подтянуты из нашей базы.', False),
    ('   • это ЗАКЛЮЧЕНИЯ экспертизы: стройка могла не начаться, а могла и закончиться.', False),
    ('', False),
    ('КОНТРОЛИ', True),
    ('   • выдуманное слово «нипрятозаумень» даёт в реестре 0 записей.', False),
    ('   • выдуманный ИНН 9999999999 в нашей базе даёт 0 контактов и 0 поводов.', False),
    ('   • сверка новизны: выдуманный ИНН обязан быть новым (оказался), взятый из базы -', False),
    ('     не новым (не оказался).', False),
    ('   • выгрузка ПОЛНАЯ: 0 недоборов на 123 слова. Неполный срез дал бы заниженное', False),
    ('     число и выглядел бы как вывод - это проверялось на каждом слове.', False),
]
for i, (t, zh) in enumerate(OPIS, start=1):
    c = ws.cell(row=i, column=1, value=t)
    c.font = ZAG if zh else OB
ws.column_dimensions['A'].width = 100

SH = ['Дата заключения', 'Регион', 'Объект', 'Отрасль', 'Приоритетная', 'Найден по слову',
      'Класс', 'Почему так помечено', 'Адрес объекта', 'Вывод экспертизы', 'Застройщик',
      'ИНН застройщика', 'Застройщик новый для базы', 'Телефонов у застройщика',
      'Из них тех.роль', 'Поводов', 'Проектировщик', 'ИНН проектировщика',
      'Проектировщик новый', 'Технический заказчик', 'Номер заключения', 'Ссылка']
SHIR = [14, 22, 60, 26, 11, 24, 26, 34, 32, 20, 40, 14, 13, 12, 12, 9, 38, 16, 13, 30, 20, 44]


def list_ob(imya, gr):
    w = wb.create_sheet(imya)
    w.append(SH)
    for x in gr:
        z, p = x.get('zastroyshchik_inn', ''), x.get('proektirovshchik_inn', '')
        w.append([x.get('data', ''), x.get('region', ''), x.get('obekt', ''),
                  x.get('otrasl', ''), x.get('prioritetnaya', ''), x.get('nayden_po', ''),
                  x.get('klass', ''), x.get('pochemu', ''), x.get('adres_obekta', ''),
                  x.get('vyvod', ''), x.get('zastroyshchik', ''), z, nov.get(z, ''),
                  po_tel.get(z, 0), po_teh.get(z, 0), po_pov.get(z, 0),
                  x.get('proektirovshchik', ''), p, nov.get(p, ''),
                  x.get('tehzakazchik', ''), x.get('nomer_zaklyucheniya', ''),
                  x.get('ssylka', '')])
    return w


w1 = list_ob('Производство', PROM)
w2 = list_ob('Приоритетные', PRIOR)
w3 = list_ob('Сомнительно', SOMN)
w4 = list_ob('Отсеяно', OTSEV)

w5 = wb.create_sheet('Предприятия')
w5.append(['ИНН', 'Предприятие', 'Отрасль', 'Регион', 'Новое для базы',
           'Производственных объектов', 'Приоритетная отрасль', 'Телефонов в базе',
           'Из них тех.роль', 'Поводов', 'Последнее заключение'])
agg = {}
for x in PROM:
    i = x.get('zastroyshchik_inn')
    if not i:
        continue
    a = agg.setdefault(i, {'imya': x['zastroyshchik'], 'otr': collections.Counter(),
                           'reg': x['region'], 'n': 0, 'pr': '', 'data': ''})
    a['otr'][x['otrasl']] += 1
    a['n'] += 1
    if x['prioritetnaya']:
        a['pr'] = 'да'
    if x['data'] > a['data']:
        a['data'] = x['data']
for i, a in sorted(agg.items(), key=lambda z: (-z[1]['n'], z[0])):
    w5.append([i, a['imya'], a['otr'].most_common(1)[0][0], a['reg'], nov.get(i, ''),
               a['n'], a['pr'], po_tel.get(i, 0), po_teh.get(i, 0), po_pov.get(i, 0),
               a['data']])

wk = wb.create_sheet('Контакты')
wk.append(['ИНН', 'Должность как в источнике', 'Роль (канон)', 'Телефон', 'Почта',
           'Источник', 'Ссылка', 'Откуда взято', 'Тех.роль'])
for k in kont:
    wk.append([k['inn'], k.get('chelovek_dolzhnost', ''), k.get('rol_kanon', ''),
               k.get('telefon', ''), k.get('pochta', ''), k.get('istochnik', ''),
               k.get('ssylka', ''), k.get('otkuda', ''), k['tehnicheskaya']])
wp = wb.create_sheet('Поводы')
wp.append(['ИНН', 'Тип события', 'Что происходит', 'Сумма', 'Источник', 'Ссылка', 'Когда'])
for p in povod:
    wp.append([p['inn'], p.get('tip_sobytiya', ''), p.get('chto', ''), p.get('summa', ''),
               p.get('istochnik', ''), p.get('ssylka', ''), p.get('kogda', '')])

SH_F = Font(name=SHRIFT, size=10, bold=True, color='FFFFFF')
SH_FILL = PatternFill('solid', fgColor='2F5496')
SHIR_DOP = {'Предприятия': [14, 54, 26, 22, 13, 13, 13, 12, 12, 9, 15],
            'Контакты': [14, 38, 18, 18, 28, 20, 44, 16, 10],
            'Поводы': [14, 22, 70, 18, 22, 44, 14]}
for w in (w1, w2, w3, w4, w5, wk, wp):
    for c in w[1]:
        c.font = SH_F
        c.fill = SH_FILL
        c.alignment = Alignment(vertical='center', wrap_text=True)
    w.freeze_panes = 'A2'
    w.auto_filter.ref = w.dimensions
    w.row_dimensions[1].height = 32
    for i, sh in enumerate(SHIR_DOP.get(w.title, SHIR), start=1):
        w.column_dimensions[get_column_letter(i)].width = sh
    for row in w.iter_rows(min_row=2):
        for c in row:
            c.font = Font(name=SHRIFT, size=10)
            c.alignment = Alignment(vertical='top')

wb.save(VYHOD)
print('файл: %s' % VYHOD)
print('  Производство %d · Приоритетные %d · Предприятия %d · Сомнительно %d · Отсеяно %d'
      % (len(PROM), len(PRIOR), len(agg), len(SOMN), len(OTSEV)))
print('  предприятий с телефоном в базе: %d из %d'
      % (len([i for i in agg if po_tel.get(i)]), len(agg)))
print('  предприятий с телефоном при технической роли: %d'
      % len([i for i in agg if po_teh.get(i)]))
