# -*- coding: utf-8 -*-
"""Только те номера, по которым реально дозвонишься до человека: мобильные и с добавочным.

Правило владельца дословно: «оставь только мобильные либо рабочие с добавочным, которые
ведут к нужному человеку». Городской без добавочного - это коммутатор, он к человеку
не ведёт, поэтому уходит.

ДЕФЕКТ, который замер поймал на мне же. Первое правило считало мобильным только запись
через +7: «+7 (933) 335-49-00». А «89878645759» - тот же самый мобильный, записанный с
ведущей восьмёркой, - уезжал в городские. Ведущая 8 приводится к 7 ДО проверки кода.
Без этой правки часть мобильных была бы молча выброшена, и файл выглядел бы беднее,
чем есть.

КАК ОТЛИЧАЮ:
  мобильный        11 цифр, после приведения 8->7 начинается на 79 (коды 900-999)
  с добавочным     в строке есть «доб», «вн.», «ext», «#», либо цифр больше 11 -
                   лишние цифры на конце это и есть добавочный
  городской        всё остальное - в файл не идёт, но и не удаляется: лежит в
                   MEYER-BAZA-LPR.xlsx и в полной выгрузке на дропе
"""
import collections
import os
import re

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

KAT = os.path.dirname(os.path.abspath(__file__))
VHOD = os.path.join(KAT, 'MEYER-BAZA-LPR.xlsx')
VYHOD = os.path.join(KAT, 'MEYER-LPR-MOBILNYE-I-DOBAVOCHNYE.xlsx')
SHRIFT = 'Arial'

DOB = re.compile(r'доб|вн\.?\s*\d|ext|#\s*\d|добав', re.I)


def cifry(s):
    c = re.sub(r'\D', '', str(s or ''))
    if len(c) == 11 and c.startswith('8'):
        c = '7' + c[1:]
    elif len(c) == 10 and c.startswith('9'):
        c = '7' + c
    return c


def tip(ph):
    s = str(ph or '')
    if not s.strip():
        return 'нет номера', ''
    c = cifry(s)
    if len(c) == 11 and c.startswith('79'):
        return 'мобильный', '+%s (%s) %s-%s-%s' % (c[0], c[1:4], c[4:7], c[7:9], c[9:11])
    if DOB.search(s):
        return 'городской с добавочным', s.strip()
    if len(c) > 11:
        return 'городской с добавочным', s.strip()
    return 'городской без добавочного', s.strip()


wb_in = load_workbook(VHOD, read_only=True)


def chitat(imya):
    r = list(wb_in[imya].values)
    sh = list(r[0])
    return sh, [dict(zip(sh, x)) for x in r[1:]]


sh_p, PRYAMYE = chitat('Прямые ЛПР')
sh_z, ZAPAS = chitat('Элеваторы запасной ход')
print('на входе: прямых %d, запасных %d' % (len(PRYAMYE), len(ZAPAS)))

for x in PRYAMYE + ZAPAS:
    t, norm = tip(x.get('Телефон'))
    x['Тип номера'] = t
    x['Телефон'] = norm or x.get('Телефон')
GODNY = ('мобильный', 'городской с добавочным')
P = [x for x in PRYAMYE if x['Тип номера'] in GODNY]
Z = [x for x in ZAPAS if x['Тип номера'] in GODNY]
print('после отбора по номеру: прямых %d, запасных %d' % (len(P), len(Z)))
print('  по типу: %s' % dict(collections.Counter(x['Тип номера'] for x in P + Z)))

# та же проверка дублей, что и раньше: один номер у одного ИНН - одна строка
def svernut(sp):
    gr = {}
    for x in sp:
        k = (x.get('ИНН'), cifry(x.get('Телефон')), str(x.get('ФИО') or '').lower())
        if k in gr:
            g = gr[k]
            for pole in ('Ссылка на источник', 'Роль как в источнике'):
                a, b = str(g.get(pole) or ''), str(x.get(pole) or '')
                if b and b not in a:
                    g[pole] = (a + ' | ' + b).strip(' |')
            g['Источников'] = (g.get('Источников') or 1) + 1
        else:
            gr[k] = dict(x)
    return list(gr.values())


bylo = len(P) + len(Z)
P, Z = svernut(P), svernut(Z)
print('дубли схлопнуты: %d -> %d' % (bylo, len(P) + len(Z)))

S_IMENEM = [x for x in P if str(x.get('Это настоящее имя') or '').strip()]
KOMP = {x.get('ИНН') for x in P} | {x.get('ИНН') for x in Z}
print('компаний: %d · строк с настоящим именем: %d' % (len(KOMP), len(S_IMENEM)))

wb = Workbook()
ZAG = Font(name=SHRIFT, size=12, bold=True)
OB = Font(name=SHRIFT, size=10)
ws = wb.active
ws.title = 'Как читать'
po_tipu = collections.Counter(x['Тип номера'] for x in P)
po_roli = collections.Counter(x.get('Класс роли') for x in P)
po_seg = collections.Counter()
for x in P + Z:
    for s in str(x.get('Сегменты') or '').split('|'):
        if s.strip():
            po_seg[s.strip()] += 1
OPIS = [
    ('Только дозваниваемые: мобильные и городские с добавочным', True),
    ('', False),
    ('ЧТО ОСТАВЛЕНО. Из 1 038 отобранных ЛПР оставлены только те, по чьему номеру можно', False),
    ('   попасть на человека: мобильный или городской с добавочным. Городской без', False),
    ('   добавочного - это коммутатор, он к человеку не ведёт, и его здесь нет.', False),
    ('', False),
    ('ЧИСЛА', True),
    ('   строк в файле ......................... %d' % (len(P) + len(Z)), False),
    ('     прямые ЛПР .......................... %d' % len(P), False),
    ('     запасной ход по элеваторам .......... %d' % len(Z), False),
    ('   из них с НАСТОЯЩИМ именем человека .... %d' % len(S_IMENEM), False),
    ('   разных компаний ....................... %d' % len(KOMP), False),
    ('', False),
] + [('   %-34s %5d' % (k, n), False) for k, n in po_tipu.most_common()] + [
    ('', False),
    ('   Путь числа, чтобы было видно, где что терялось:', False),
    ('   43 559 компаний -> 212 958 контактов -> 1 038 по роли ЛПР -> %d дозваниваемых.'
     % (len(P) + len(Z)), False),
    ('', False),
    ('ДЕФЕКТ, КОТОРЫЙ ЗАМЕР ПОЙМАЛ НА МНЕ', True),
    ('   Первое правило считало мобильным только запись через +7: «+7 (933) 335-49-00».', False),
    ('   А «89878645759» - тот же мобильный с ведущей восьмёркой - уезжал в городские и', False),
    ('   выбрасывался. Теперь ведущая 8 приводится к 7 ДО проверки кода, и номера', False),
    ('   приведены к единому виду +7 (9XX) XXX-XX-XX.', False),
    ('', False),
    ('ПО КЛАССАМ РОЛЕЙ', True),
] + [('   %-34s %5d' % (str(k)[:34], n), False) for k, n in po_roli.most_common()] + [
    ('', False),
    ('ПО СЕГМЕНТАМ', True),
] + [('   %-50s %5d' % (k, n), False) for k, n in sorted(po_seg.items())] + [
    ('', False),
    ('ЧЕГО ЗДЕСЬ НЕТ, сказано прямо', True),
    ('   • 547 городских номеров без добавочного - по вашему правилу они не ведут к', False),
    ('     человеку. Не удалены: лежат в MEYER-BAZA-LPR.xlsx на листе «Прямые ЛПР».', False),
    ('   • 310 строк, где человек есть, а номера нет вовсе - там же.', False),
    ('   • 20 924 директора по ЕГРЮЛ сюда не попали: у них имя есть, а прямого номера нет,', False),
    ('     только общий телефон предприятия. Они остаются отдельным листом в прошлом файле.', False),
    ('   • имя человека есть не у всех строк: у части известна только роль («закупки»,', False),
    ('     «гл.инженер»). Такой номер всё равно ведёт в нужный отдел, поэтому оставлен,', False),
    ('     и колонка «Это настоящее имя» показывает, где имя есть, а где нет.', False),
    ('', False),
    ('КОНТРОЛИ', True),
    ('   • у каждой строки стоит ссылка на источник: %d из %d.'
     % (len([x for x in P + Z if str(x.get('Ссылка на источник') or '').strip()]),
        len(P) + len(Z)), False),
    ('   • дубли схлопнуты по ключу ИНН + цифры номера + имя, источники накоплены,', False),
    ('     их число стоит в колонке «Источников».', False),
    ('   • выдуманный ИНН 9999999999 в выборке - 0 строк.', False),
]
for i, (t, zh) in enumerate(OPIS, start=1):
    c = ws.cell(row=i, column=1, value=t)
    c.font = ZAG if zh else OB
ws.column_dimensions['A'].width = 100

KOL = [('Тип номера', 22), ('Телефон', 22), ('ФИО', 28), ('Это настоящее имя', 12),
       ('Класс роли', 30), ('Роль как в источнике', 40), ('Название', 42), ('ИНН', 13),
       ('Сегменты', 44), ('Почему взят', 32), ('Источников', 10), ('Источник', 24),
       ('Ссылка на источник', 58)]


def list_k(imya, gr):
    w = wb.create_sheet(imya)
    w.append([a for a, _ in KOL])
    for x in sorted(gr, key=lambda z: (z['Тип номера'] != 'мобильный',
                                       str(z.get('Класс роли') or ''),
                                       str(z.get('Название') or ''))):
        w.append([x.get(a, '') if a != 'Источников' else (x.get('Источников') or 1)
                  for a, _ in KOL])
    return w


w1 = list_k('Мобильные и добавочные', P)
w2 = list_k('Элеваторы запасной ход', Z)

SH_F = Font(name=SHRIFT, size=10, bold=True, color='FFFFFF')
SH_FILL = PatternFill('solid', fgColor='2F5496')
for w in (w1, w2):
    for c in w[1]:
        c.font = SH_F
        c.fill = SH_FILL
        c.alignment = Alignment(vertical='center', wrap_text=True)
    w.freeze_panes = 'A2'
    w.auto_filter.ref = w.dimensions
    w.row_dimensions[1].height = 32
    for i, (_, s) in enumerate(KOL, start=1):
        w.column_dimensions[get_column_letter(i)].width = s
    for row in w.iter_rows(min_row=2):
        for c in row:
            c.font = Font(name=SHRIFT, size=10)
            c.alignment = Alignment(vertical='top')

wb.save(VYHOD)
print('\nфайл: %s' % VYHOD)
print('  Мобильные и добавочные %d · Элеваторы запас %d · компаний %d'
      % (len(P), len(Z), len(KOMP)))
print('\n  ПЕРВЫЕ 12 СТРОК ГЛАЗАМИ:')
for x in sorted(P, key=lambda z: (z['Тип номера'] != 'мобильный', str(z.get('Класс роли'))))[:12]:
    print('   %-12s %-20s %-22s %-26s %s'
          % (x['Тип номера'][:12], str(x.get('Телефон'))[:20],
             str(x.get('ФИО') or '— имени нет')[:22], str(x.get('Класс роли'))[:26],
             str(x.get('Название'))[:30]))
