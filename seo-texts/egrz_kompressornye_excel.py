# -*- coding: utf-8 -*-
"""Эксель по тем, кто СТРОИТ КОМПРЕССОРНУЮ: объекты, проектировщики, поводы, телефоны.

Заказ владельца дословно: «все данные тех кто строит компрессорную, их проектировщики,
новостные поводы, номера телефонов есть если тех роли».

Откуда что взято:
  лист «Объекты»  — ЕГРЗ, реестр заключений экспертизы проектной документации. Выгрузка по
                    пяти словам через tolower(contains(...)), контроль выдуманным словом 0.
  лист «Контакты» — наша живая база enrich.db: таблицы people и phone_contacts по ИНН.
  лист «Поводы»   — таблица signals по тем же ИНН.

Признак технической роли ставится в питоне по словарю (это разметка текста, не расчёт).
Счётчики на листе «Объекты» тоже посчитаны в питоне: формулами это 2 475 COUNTIFS, которые
LibreOffice не пересчитал ни за 175 секунд, ни за 600. Это выгрузка на дату, а не модель.
"""
import csv
import io
import json
import os
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

KAT = os.path.dirname(os.path.abspath(__file__))
OBEKTY = os.path.join(KAT, 'KOMPRESSORNYE-EGRZ.jsonl')
KONTAKTY = os.path.join(KAT, '3s_KOMP-KONTAKTY.csv')
POVODY = os.path.join(KAT, '3s_KOMP-POVODY.csv')
VYHOD = os.path.join(KAT, 'KOMPRESSORNYE-STANCII-EGRZ.xlsx')

TEH = re.compile(r'инженер|энергетик|механик|технолог|техдирект|техн|производств|цех|'
                 r'КИПиА|АСУ|снабжен|закупк|заказчик|капитальн|проект|эксплуатац', re.I)
SHRIFT = 'Arial'

obekty = [json.loads(s) for s in io.open(OBEKTY, encoding='utf-8') if s.strip()]
kont = list(csv.DictReader(io.open(KONTAKTY, encoding='utf-8-sig'), delimiter=';'))
povod = list(csv.DictReader(io.open(POVODY, encoding='utf-8-sig'), delimiter=';'))
print('объектов %d, контактов %d, поводов %d' % (len(obekty), len(kont), len(povod)))

for k in kont:
    tekst = (k.get('chelovek_dolzhnost') or '') + ' ' + (k.get('rol_kanon') or '')
    k['tehnicheskaya'] = 'да' if TEH.search(tekst) else ''
print('из контактов помечены технической ролью: %d' % len([k for k in kont if k['tehnicheskaya']]))

wb = Workbook()

# ---------------------------------------------------------------- лист «Как читать»
ws = wb.active
ws.title = 'Как читать'
ZAGOL = Font(name=SHRIFT, size=12, bold=True)
OBYCH = Font(name=SHRIFT, size=10)
stroki_opisi = [
    ('Кто строит компрессорные станции: объекты, проектировщики, поводы, контакты', True),
    ('', False),
    ('ЛИСТ «Объекты» — реестр заключений экспертизы проектной документации (ЕГРЗ, egrz.ru).', False),
    ('   Для нас там главное: в одной записи стоят ОБЕ стороны с ИНН — застройщик, то есть', False),
    ('   будущий эксплуатант, и ПРОЕКТИРОВЩИК, который на стадии проекта и выбирает', False),
    ('   оборудование. Раньше проектировщик у нас был предположением, теперь это строка с ИНН.', False),
    ('', False),
    ('ЛИСТ «Контакты» — то, что уже есть в нашей базе по этим ИНН: люди с должностями,', False),
    ('   телефоны, почты. Колонка «тех.роль» = да, если должность или роль техническая.', False),
    ('   Владелец просил телефоны «если есть тех роли» — сортируйте по этой колонке.', False),
    ('', False),
    ('ЛИСТ «Поводы» — новостные и закупочные события по тем же ИНН из нашей базы сигналов.', False),
    ('', False),
    ('ЧТО ЭТОТ ФАЙЛ НЕ СОДЕРЖИТ, сказано прямо:', True),
    ('   • людей в самом ЕГРЗ нет вовсе — ни телефонов, ни ФИО. Контакты подтянуты из нашей', False),
    ('     базы, и только для тех ИНН, которые в ней уже были.', False),
    ('   • марка машины в ЕГРЗ встречается редко, около 4 % записей. Что именно за компрессор', False),
    ('     стоит или будет стоять, по этому источнику не определить.', False),
    ('   • контакты не перепроверялись открытием страниц в этом прогоне: у каждой строки', False),
    ('     стоит источник и ссылка того прогона, которым она добыта.', False),
    ('', False),
    ('КОНТРОЛИ, без которых числам верить нельзя:', True),
    ('   • выдуманное слово «щварцкопфер» в ЕГРЗ даёт 0 записей — поиск различает слова.', False),
    ('   • выдуманный ИНН 9999999999 в нашей базе даёт 0 контактов и 0 поводов.', False),
    ('   • поиск ведётся ТОЛЬКО через tolower(): contains() в ЕГРЗ регистрозависим, и наивный', False),
    ('     поиск теряет четверть находок («компрессорная» 208, «Компрессорная» 65, tolower 274).', False),
    ('', False),
    ('ПРО ПЯТЬ ПОСЛЕДНИХ КОЛОНОК листа «Объекты»: они посчитаны на дату выгрузки и лежат', False),
    ('   числами, а не формулами. Формулами это 2 475 COUNTIFS по диапазону в 2 123 строки —', False),
    ('   такой файл пересчитывается минутами и у вас открывался бы так же долго. Это снимок,', False),
    ('   а не модель: если правите данные на листах, счётчики сами не изменятся.', False),
]
for i, (t, zhirno) in enumerate(stroki_opisi, start=1):
    c = ws.cell(row=i, column=1, value=t)
    c.font = ZAGOL if zhirno else OBYCH
ws.column_dimensions['A'].width = 105

# ---------------------------------------------------------------- лист «Объекты»
wo = wb.create_sheet('Объекты')
SHAPKA_O = ['Дата заключения', 'Регион', 'Объект', 'Адрес объекта', 'Вывод экспертизы',
            'Вид документа', 'Застройщик', 'ИНН застройщика', 'Адрес застройщика',
            'Проектировщик', 'ИНН проектировщика', 'Адрес проектировщика',
            'Технический заказчик', 'ИНН техзаказчика', 'Найден по слову',
            'Номер заключения', 'Ссылка на карточку',
            'Телефонов у застройщика', 'Из них тех.роль', 'Поводов у застройщика',
            'Телефонов у проектировщика', 'Из них тех.роль']
wo.append(SHAPKA_O)
obekty.sort(key=lambda z: z.get('data') or '', reverse=True)
for z in obekty:
    wo.append([z.get('data', ''), z.get('region', ''), z.get('obekt', ''),
               z.get('adres_obekta', ''), z.get('vyvod', ''), z.get('vid_dokumenta', ''),
               z.get('zastroyshchik', ''), z.get('zastroyshchik_inn', ''),
               z.get('zastroyshchik_adres', ''),
               z.get('proektirovshchik', ''), z.get('proektirovshchik_inn', ''),
               z.get('proektirovshchik_adres', ''),
               z.get('tehzakazchik', ''), z.get('tehzakazchik_inn', ''),
               z.get('nayden_po', ''), z.get('nomer_zaklyucheniya', ''), z.get('ssylka', '')])
# СЧЁТЧИКИ СЧИТАЮТСЯ В ПИТОНЕ, А НЕ ФОРМУЛАМИ, и вот почему.
# Сперва я поставила COUNTIFS в каждую строку: 2 475 формул по диапазону в 2 123 строки.
# LibreOffice не пересчитал их ни за 175 секунд, ни за 600, а непересчитанная формула
# читается как пусто любым, кто смотрит кэш. У владельца файл открывался бы так же долго.
# Это выгрузка на дату, а не модель: данные в ней не правят, пересчитывать нечего.
# Поэтому числа кладутся значениями, а в легенде сказано, что они посчитаны на дату.
po_tel, po_teh, po_pov = {}, {}, {}
for k in kont:
    i = k.get('inn', '')
    if (k.get('telefon') or '').strip():
        po_tel[i] = po_tel.get(i, 0) + 1
    if k.get('tehnicheskaya'):
        po_teh[i] = po_teh.get(i, 0) + 1
for pv in povod:
    i = pv.get('inn', '')
    po_pov[i] = po_pov.get(i, 0) + 1
for r, z in enumerate(obekty, start=2):
    zi = z.get('zastroyshchik_inn', '')
    pi = z.get('proektirovshchik_inn', '')
    wo.cell(row=r, column=18, value=po_tel.get(zi, 0))
    wo.cell(row=r, column=19, value=po_teh.get(zi, 0))
    wo.cell(row=r, column=20, value=po_pov.get(zi, 0))
    wo.cell(row=r, column=21, value=po_tel.get(pi, 0))
    wo.cell(row=r, column=22, value=po_teh.get(pi, 0))
print('ЗАСТРОЙЩИКИ: с телефонами %d объектов, с тех.ролью %d, с поводами %d'
      % (len([z for z in obekty if po_tel.get(z.get('zastroyshchik_inn', ''))]),
         len([z for z in obekty if po_teh.get(z.get('zastroyshchik_inn', ''))]),
         len([z for z in obekty if po_pov.get(z.get('zastroyshchik_inn', ''))])))
print('ПРОЕКТИРОВЩИКИ: с телефонами %d объектов, с тех.ролью %d'
      % (len([z for z in obekty if po_tel.get(z.get('proektirovshchik_inn', ''))]),
         len([z for z in obekty if po_teh.get(z.get('proektirovshchik_inn', ''))])))

# ---------------------------------------------------------------- лист «Контакты»
wk = wb.create_sheet('Контакты')
wk.append(['ИНН', 'Должность как в источнике', 'Роль (канон)', 'Телефон', 'Почта',
           'Источник', 'Ссылка', 'Откуда взято', 'Тех.роль'])
for k in kont:
    wk.append([k.get('inn', ''), k.get('chelovek_dolzhnost', ''), k.get('rol_kanon', ''),
               k.get('telefon', ''), k.get('pochta', ''), k.get('istochnik', ''),
               k.get('ssylka', ''), k.get('otkuda', ''), k.get('tehnicheskaya', '')])

# ---------------------------------------------------------------- лист «Поводы»
wp = wb.create_sheet('Поводы')
wp.append(['ИНН', 'Тип события', 'Что происходит', 'Сумма', 'Источник', 'Ссылка', 'Когда'])
for p in povod:
    wp.append([p.get('inn', ''), p.get('tip_sobytiya', ''), p.get('chto', ''),
               p.get('summa', ''), p.get('istochnik', ''), p.get('ssylka', ''),
               p.get('kogda', '')])

# ---------------------------------------------------------------- оформление
SHAPKA_FONT = Font(name=SHRIFT, size=10, bold=True, color='FFFFFF')
SHAPKA_FILL = PatternFill('solid', fgColor='2F5496')
SHIRINA = {
    'Объекты': [14, 22, 60, 40, 22, 22, 42, 14, 34, 42, 16, 34, 34, 15, 16, 22, 46, 12, 12, 12, 13, 12],
    'Контакты': [14, 38, 18, 18, 28, 20, 46, 16, 10],
    'Поводы': [14, 22, 70, 18, 22, 46, 14],
}
for ws_ in (wo, wk, wp):
    for c in ws_[1]:
        c.font = SHAPKA_FONT
        c.fill = SHAPKA_FILL
        c.alignment = Alignment(vertical='center', wrap_text=True)
    ws_.freeze_panes = 'A2'
    ws_.auto_filter.ref = ws_.dimensions
    ws_.row_dimensions[1].height = 30
    for i, w in enumerate(SHIRINA[ws_.title], start=1):
        ws_.column_dimensions[get_column_letter(i)].width = w
    for row in ws_.iter_rows(min_row=2):
        for c in row:
            c.font = Font(name=SHRIFT, size=10)
            c.alignment = Alignment(vertical='top', wrap_text=False)

wb.save(VYHOD)
print('файл собран: %s' % VYHOD)
print('  лист Объекты:  %d строк' % len(obekty))
print('  лист Контакты: %d строк' % len(kont))
print('  лист Поводы:   %d строк' % len(povod))
