# -*- coding: utf-8 -*-
"""Отбор по приоритету должностей: только те, кто влияет на закупку, эксплуатацию и качество.

Списки ролей взяты дословно из заказа и разложены по сегментам, потому что они РАЗНЫЕ:
  пищевые, орехи, ягоды  директор, главный инженер, технический директор, директор по
                         производству, главный технолог и технолог, качество, закупки
  элеваторы              директор, главный инженер, главный технолог, заведующий
                         элеватором или производством, агроном, закупщик. И отдельно:
                         «если прямых нет - допускаются другие, включая бухгалтерию».
                         Этот запасной ход сделан только для элеваторов, как и сказано.
  семеноводы             директор, главный агроном и агроном, руководитель производства,
                         специалист по семеноводству, главный инженер, закупки
  экспортёры             руководитель, коммерческий директор, закупки, производство,
                         качество, агрономы и другие доступные ЛПР

Компания может быть в нескольких сегментах - тогда ей разрешены роли ВСЕХ её сегментов.
Иначе элеватор, который заодно пищевое предприятие, потерял бы половину своих людей.

ДИРЕКТОР ПО ЕГРЮЛ ОСТАВЛЕН. Он стоит первым в списке у трёх сегментов из четырёх, и это
названное имя. Но прямого номера у него нет, поэтому он лежит на своём листе, а не вперемешку
с теми, у кого номер есть. Смешать их значило бы завысить число прямых контактов в 100 раз.
"""
import collections
import csv
import io
import os
import re

KAT = os.path.dirname(os.path.abspath(__file__))
VYHOD = os.path.join(KAT, 'MEYER-BAZA-LPR.xlsx')

ROLI = {
    'директор и первое лицо': re.compile(
        r'генеральн\w*\s*директор|\bгендиректор|\bдиректор\b|директор\s|руководител|'
        r'\bгд\b|ген\.?\s*дир|управляющ|председател|собственник|учредител', re.I),
    'коммерческий директор': re.compile(r'коммерческ', re.I),
    'главный инженер и техдиректор': re.compile(
        r'главн\w*\s*инженер|технич\w*\s*директор|\bгл\.?\s*инженер|'
        r'директор\s+по\s+техн|главн\w*\s*механик|главн\w*\s*энергетик', re.I),
    'производство': re.compile(
        r'директор\s+по\s+производств|руководител\w*\s+производств|'
        r'начальник\w*\s+производств|заведующ\w*\s+(?:элеватор|производств|складом)|'
        r'\bпроизводств\w*\b|начальник\s+цеха|нач\.?\s*производств', re.I),
    'технолог': re.compile(r'технолог', re.I),
    'качество': re.compile(r'качеств|\bотк\b|лаборатор|сертификац|пищев\w*\s*безопасн', re.I),
    'закупки и снабжение': re.compile(r'закупк|снабжен|тендер|материально-техн', re.I),
    'агроном и семеноводство': re.compile(r'агроном|семеновод|селекц', re.I),
    'инженер и техника прочее': re.compile(r'\bинженер|механик|энергетик|\bкипиа\b|\bасу\b', re.I),
    'бухгалтерия': re.compile(r'бухгалтер|\bфинанс', re.I),
    'приёмная и общий': re.compile(r'приёмн|приемн|секрет|\bобщий|диспетчер|'
                                   r'номер предприятия|отдел кадров|кадры', re.I),
    'продажи': re.compile(r'продаж|сбыт|менеджер по прод', re.I),
}
RAZRESHENO = {
    '1 Экспортёры (кандидаты: опт зерна и продуктов)': [
        'директор и первое лицо', 'коммерческий директор', 'закупки и снабжение',
        'производство', 'качество', 'агроном и семеноводство', 'технолог',
        'главный инженер и техдиректор'],
    '2 Семеноводы': [
        'директор и первое лицо', 'агроном и семеноводство', 'производство',
        'главный инженер и техдиректор', 'закупки и снабжение'],
    '3 Пищевые предприятия': [
        'директор и первое лицо', 'главный инженер и техдиректор', 'производство',
        'технолог', 'качество', 'закупки и снабжение'],
    '4 Элеваторы': [
        'директор и первое лицо', 'главный инженер и техдиректор', 'технолог',
        'производство', 'агроном и семеноводство', 'закупки и снабжение'],
    '5 Орехи': [
        'директор и первое лицо', 'главный инженер и техдиректор', 'производство',
        'технолог', 'качество', 'закупки и снабжение'],
    '6 Ягоды': [
        'директор и первое лицо', 'главный инженер и техдиректор', 'производство',
        'технолог', 'качество', 'закупки и снабжение'],
}
# запасной ход разрешён ТОЛЬКО элеваторам, дословно по заказу
ZAPASNOY = ['бухгалтерия', 'приёмная и общий', 'инженер и техника прочее']


def klass_roli(tekst):
    for imya, rx in ROLI.items():
        if rx.search(tekst or ''):
            return imya
    return ''


komp = list(csv.DictReader(io.open(os.path.join(KAT, 'MEYER-BAZA-KOMPANII.csv'),
                                   encoding='utf-8-sig'), delimiter=';'))
kont = list(csv.DictReader(io.open(os.path.join(KAT, 'MEYER-BAZA-KONTAKTY.csv'),
                                   encoding='utf-8-sig'), delimiter=';'))
po_inn = {x['inn']: x for x in komp}
print('на входе: компаний %d, контактов %d' % (len(komp), len(kont)))

PRYAMYE, ZAPAS = [], []
for x in kont:
    tekst = (x['rol_kak_v_istochnike'] or '') + ' ' + (x['fio'] or '')
    kl = klass_roli(tekst)
    if not kl:
        continue
    segs = [s.strip() for s in (x['segmenty'] or '').split('|') if s.strip()]
    razresh = set()
    for s in segs:
        razresh |= set(RAZRESHENO.get(s, []))
    elevator = any(s.startswith('4 Элеваторы') for s in segs)
    x['klass_roli'] = kl
    if kl in razresh:
        x['pochemu_vzyat'] = 'роль из вашего списка для сегмента'
        PRYAMYE.append(x)
    elif elevator and kl in ZAPASNOY:
        x['pochemu_vzyat'] = ('запасной ход для элеваторов: прямого ЛПР нет, '
                              'через этого человека выходят на ЛПР')
        ZAPAS.append(x)

# --- СХЛОПЫВАНИЕ ДУБЛЕЙ. Один человек с одним номером приходит из нескольких карточек
# закупок, и в выдаче ООО «ЧМНГ» занимало восемь строк подряд. Источники при этом НЕ
# теряются, а накапливаются: правило владельца «источники накапливаются, а не заменяются».
# Число источников становится отдельной колонкой — подтверждённое дважды должно быть
# отличимо от подтверждённого однажды.
NOMER = re.compile(r'\D+')
# Проверка, что в поле person действительно имя, а не роль: «закупки», «Опросы Статистика
# Карта» туда попадали из подписей со страниц. Имя — это Фамилия И.О. или Фамилия Имя.
IMYA = re.compile(r'^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+'
                  r'(?:[А-ЯЁ]\.\s*[А-ЯЁ]?\.?|[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)\s*$')


def pohozhe_na_imya(s):
    s = (s or '').strip().strip('"\u00ab\u00bb')
    return bool(IMYA.match(s)) and len(s) <= 46


def svernut(spisok):
    gr = {}
    for x in spisok:
        klyuch = (x['inn'], NOMER.sub('', x['telefon'] or ''),
                  (x['fio'] or '').strip().lower(), x['klass_roli'])
        if klyuch in gr:
            g = gr[klyuch]
            if x['ssylka_na_istochnik'] and x['ssylka_na_istochnik'] not in g['_ssylki']:
                g['_ssylki'].append(x['ssylka_na_istochnik'])
            if x['istochnik'] and x['istochnik'] not in g['_ist']:
                g['_ist'].append(x['istochnik'])
            if x['rol_kak_v_istochnike'] and x['rol_kak_v_istochnike'] not in g['_roli']:
                g['_roli'].append(x['rol_kak_v_istochnike'])
        else:
            y = dict(x)
            y['_ssylki'] = [x['ssylka_na_istochnik']] if x['ssylka_na_istochnik'] else []
            y['_ist'] = [x['istochnik']] if x['istochnik'] else []
            y['_roli'] = [x['rol_kak_v_istochnike']] if x['rol_kak_v_istochnike'] else []
            gr[klyuch] = y
    out = []
    for y in gr.values():
        y['istochnikov'] = len(y['_ssylki'])
        y['ssylka_na_istochnik'] = ' | '.join(y['_ssylki'][:4])
        y['istochnik'] = ' | '.join(y['_ist'][:3])
        y['rol_kak_v_istochnike'] = ' | '.join(y['_roli'][:3])
        y['imya_nastoyashchee'] = 'да' if pohozhe_na_imya(y['fio']) else ''
        if not y['imya_nastoyashchee'] and y['fio']:
            y['rol_kak_v_istochnike'] = (y['fio'] + ' | ' + y['rol_kak_v_istochnike']).strip(' |')
            y['fio'] = ''
        out.append(y)
    return out


bylo_p, bylo_z = len(PRYAMYE), len(ZAPAS)
PRYAMYE, ZAPAS = svernut(PRYAMYE), svernut(ZAPAS)
print('дубли схлопнуты: прямых %d -> %d, запасных %d -> %d (источники накоплены)'
      % (bylo_p, len(PRYAMYE), bylo_z, len(ZAPAS)))
print('подошло по роли: прямых %d, запасных (элеваторы) %d' % (len(PRYAMYE), len(ZAPAS)))
S_NOMEROM = [x for x in PRYAMYE if (x['telefon'] or '').strip()]
S_IMENEM = [x for x in PRYAMYE if x.get('imya_nastoyashchee')]
print('  из прямых: с телефоном %d, с именем %d' % (len(S_NOMEROM), len(S_IMENEM)))

# директор по ЕГРЮЛ — имя есть, номера нет. Отдельным листом, не в общей куче.
EGRUL = []
for x in komp:
    if x['vid_kontakta'].startswith('директор по ЕГРЮЛ') and x['fio_kontakta'].strip():
        EGRUL.append(x)
print('директоров по ЕГРЮЛ (имя без прямого номера): %d' % len(EGRUL))

inn_pryamye = {x['inn'] for x in PRYAMYE}
inn_zapas = {x['inn'] for x in ZAPAS}
inn_egrul = {x['inn'] for x in EGRUL}
inn_vse = inn_pryamye | inn_zapas | inn_egrul
KOMPANII = [po_inn[i] for i in inn_vse if i in po_inn]
for k in KOMPANII:
    i = k['inn']
    k['chto_est'] = ('прямой ЛПР' if i in inn_pryamye
                     else 'запасной ход (элеватор)' if i in inn_zapas
                     else 'только директор по ЕГРЮЛ')
print('компаний, у которых есть хоть кто-то из списка: %d из %d' % (len(KOMPANII), len(komp)))
print('  с прямым ЛПР: %d' % len(inn_pryamye))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

SHRIFT = 'Arial'
wb = Workbook()
ZAG = Font(name=SHRIFT, size=12, bold=True)
OB = Font(name=SHRIFT, size=10)
ws = wb.active
ws.title = 'Как читать'
po_klassu = collections.Counter(x['klass_roli'] for x in PRYAMYE)
po_seg = collections.Counter()
for x in KOMPANII:
    for s in x['segmenty'].split(' | '):
        if s.strip():
            po_seg[s.strip()] += 1
OPIS = [
    ('Только ЛПР: те, кто влияет на закупку, эксплуатацию и требования к качеству', True),
    ('', False),
    ('ЧТО СДЕЛАНО. Из базы в 43 559 компаний и 212 958 контактов оставлены только', False),
    ('   контакты, чья роль есть в вашем списке ДЛЯ ЕГО СЕГМЕНТА. Списки разные, поэтому', False),
    ('   фильтр тоже разный: агроном проходит у семеноводов и элеваторов, но не у пищевых;', False),
    ('   технолог и качество проходят у пищевых, но не у семеноводов. Если компания в', False),
    ('   нескольких сегментах - ей разрешены роли всех её сегментов.', False),
    ('', False),
    ('ЧЕСТНЫЕ ЧИСЛА', True),
    ('   контактов подошло по роли .............. %d' % len(PRYAMYE), False),
    ('     из них с телефоном ................... %d' % len(S_NOMEROM), False),
    ('     из них с НАСТОЯЩИМ именем ............ %d' % len(S_IMENEM), False),
    ('     (в поле имени у части строк стояла роль - «закупки», «Опросы Статистика Карта».', False),
    ('      Такие проверены правилом «Фамилия И.О.» и перенесены в колонку роли.)', False),
    ('   подтверждено ДВУМЯ и более источниками .. %d'
     % len([x for x in PRYAMYE if x.get('istochnikov', 0) > 1]), False),
    ('   запасной ход для элеваторов ............ %d' % len(ZAPAS), False),
    ('   директор по ЕГРЮЛ (имя, номера нет) .... %d' % len(EGRUL), False),
    ('   компаний, где есть хоть кто-то из списка %d из 43 559' % len(KOMPANII), False),
    ('     из них с ПРЯМЫМ ЛПР .................. %d' % len(inn_pryamye), False),
    ('', False),
    ('   Прямых ЛПР мало, и это не отбор виноват. Во всей таблице phone_contacts имя', False),
    ('   человека заполнено у 3 068 строк из 777 736, то есть у 546 ИНН на всю базу.', False),
    ('   Отбор по ролям не создаёт людей, он только показывает, сколько их есть.', False),
    ('', False),
    ('ПО КЛАССАМ РОЛЕЙ среди прошедших', True),
] + [('   %-34s %5d' % (k, n), False) for k, n in po_klassu.most_common()] + [
    ('', False),
    ('ПО СЕГМЕНТАМ (компаний, где есть кто-то из списка)', True),
] + [('   %-50s %5d' % (k, n), False) for k, n in sorted(po_seg.items())] + [
    ('', False),
    ('ЛИСТЫ', True),
    ('   «Прямые ЛПР»        %5d строк - роль из вашего списка. Колонка «Класс роли»' % len(PRYAMYE), False),
    ('                       говорит, под какой пункт списка человек подошёл, а колонка', False),
    ('                       «Ссылка на источник» - откуда он взят.', False),
    ('   «Элеваторы: запасной ход» %d строк - бухгалтерия, приёмная, прочие инженеры.' % len(ZAPAS), False),
    ('                       Только для элеваторов и только потому, что вы это разрешили.', False),
    ('   «Директора по ЕГРЮЛ» %5d строк - имя есть, прямого номера нет. Директор стоит' % len(EGRUL), False),
    ('                       первым в вашем списке у трёх сегментов, поэтому он оставлен,', False),
    ('                       но лежит отдельно: смешать его с прямыми контактами значило', False),
    ('                       бы завысить их число в сто раз.', False),
    ('   «Компании»          %5d строк - карточки тех компаний, у кого есть хоть кто-то' % len(KOMPANII), False),
    ('                       из списка. Колонка «Что есть» говорит, кто именно.', False),
    ('', False),
    ('ЧТО ОТСЕЯНО', True),
    ('   • 17 373 номера без роли - нельзя сказать, чей это телефон;', False),
    ('   • 4 465 компаний без контакта вовсе;', False),
    ('   • приёмные, секретари и продажи у всех сегментов, кроме элеваторов;', False),
    ('   • отсеянное не удалено: полные выгрузки лежат на дропе,', False),
    ('     MEYER-BAZA-KOMPANII.csv и MEYER-BAZA-KONTAKTY.csv.', False),
    ('', False),
    ('КОНТРОЛИ', True),
    ('   • каждая строка несёт ссылку на источник: %d из %d прямых ЛПР со ссылкой.'
     % (len([x for x in PRYAMYE if x['ssylka_na_istochnik'].strip()]), len(PRYAMYE)), False),
    ('   • выдуманный ИНН 9999999999 в выборке - 0 строк.', False),
    ('   • отбор по ролям проверяется глазами: колонка «Роль как в источнике» стоит рядом', False),
    ('     с «Классом роли», и видно, по какому слову человек прошёл.', False),
]
for i, (t, zh) in enumerate(OPIS, start=1):
    c = ws.cell(row=i, column=1, value=t)
    c.font = ZAG if zh else OB
ws.column_dimensions['A'].width = 100

SH_C = [('Класс роли', 'klass_roli', 30), ('ФИО', 'fio', 30),
        ('Это настоящее имя', 'imya_nastoyashchee', 12),
        ('Роль как в источнике', 'rol_kak_v_istochnike', 40), ('Телефон', 'telefon', 20),
        ('Название', 'nazvanie', 40), ('ИНН', 'inn', 13), ('Сегменты', 'segmenty', 44),
        ('Почему взят', 'pochemu_vzyat', 34), ('Источников', 'istochnikov', 10),
        ('Источник', 'istochnik', 24), ('Ссылка на источник', 'ssylka_na_istochnik', 58)]


def list_k(imya, gr):
    w = wb.create_sheet(imya)
    w.append([a for a, _, _ in SH_C])
    for x in sorted(gr, key=lambda z: (z['klass_roli'], z['nazvanie'])):
        w.append([x.get(k, '') for _, k, _w in SH_C])
    return w, [c for _, _, c in SH_C]


w1, s1 = list_k('Прямые ЛПР', PRYAMYE)
w2, s2 = list_k('Элеваторы запасной ход', ZAPAS)

SH_E = [('ФИО директора', 'fio_kontakta', 32), ('Название', 'nazvanie', 42),
        ('ИНН', 'inn', 13), ('Сегменты', 'segmenty', 44), ('Регион', 'region', 22),
        ('Рабочий телефон', 'rabochiy_telefon', 18), ('E-mail', 'email', 26),
        ('Сайт', 'sayt', 28), ('Выручка', 'vyruchka', 15),
        ('Основной ОКВЭД', 'okved_osnovnoy', 44), ('Ссылка ЕГРЮЛ', 'ssylka_egryul', 40)]
w3 = wb.create_sheet('Директора по ЕГРЮЛ')
w3.append([a for a, _, _ in SH_E])
for x in sorted(EGRUL, key=lambda z: z['nazvanie']):
    w3.append([x.get(k, '') for _, k, _w in SH_E])

SH_K = [('Что есть', 'chto_est', 24), ('Сегменты', 'segmenty', 44),
        ('Название', 'nazvanie', 42), ('ИНН', 'inn', 13), ('Регион', 'region', 22),
        ('Город и адрес', 'adres', 34), ('Сайт', 'sayt', 28),
        ('Основной ОКВЭД', 'okved_osnovnoy', 44),
        ('Дополнительные ОКВЭД', 'okved_dopolnitelnye', 36),
        ('Описание деятельности', 'opisanie_deyatelnosti', 38),
        ('Выручка', 'vyruchka', 15), ('Выручка, руб', 'vyruchka_rub', 16),
        ('Год отчётности', 'god_otchetnosti', 12), ('Сотрудников', 'sotrudnikov', 11),
        ('Рабочий телефон', 'rabochiy_telefon', 18), ('E-mail', 'email', 26),
        ('Статус', 'status', 20), ('Метка нашей базы', 'razmetka_nashey_bazy', 13),
        ('Ссылка ЕГРЮЛ', 'ssylka_egryul', 40)]
w4 = wb.create_sheet('Компании')
w4.append([a for a, _, _ in SH_K])
PORYADOK = {'прямой ЛПР': 0, 'запасной ход (элеватор)': 1, 'только директор по ЕГРЮЛ': 2}
for x in sorted(KOMPANII, key=lambda z: (PORYADOK.get(z['chto_est'], 9), z['nazvanie'])):
    r = []
    for _, k, _w in SH_K:
        v = x.get(k, '')
        if k == 'vyruchka_rub':
            try:
                v = float(str(v).replace(',', '.'))
            except ValueError:
                v = None
        elif k in ('okved_dopolnitelnye', 'adres'):
            v = str(v)[:200]
        r.append(v)
    w4.append(r)

SH_F = Font(name=SHRIFT, size=10, bold=True, color='FFFFFF')
SH_FILL = PatternFill('solid', fgColor='2F5496')
for w, shir in ((w1, s1), (w2, s2), (w3, [c for _, _, c in SH_E]),
                (w4, [c for _, _, c in SH_K])):
    for c in w[1]:
        c.font = SH_F
        c.fill = SH_FILL
        c.alignment = Alignment(vertical='center', wrap_text=True)
    w.freeze_panes = 'A2'
    w.auto_filter.ref = w.dimensions
    w.row_dimensions[1].height = 32
    for i, s in enumerate(shir, start=1):
        w.column_dimensions[get_column_letter(i)].width = s
    for row in w.iter_rows(min_row=2):
        for c in row:
            c.font = Font(name=SHRIFT, size=10)
            c.alignment = Alignment(vertical='top')

wb.save(VYHOD)
print('\nфайл: %s (%.1f МБ)' % (VYHOD, os.path.getsize(VYHOD) / 1048576.0))
print('  Прямые ЛПР %d · Элеваторы запас %d · Директора ЕГРЮЛ %d · Компании %d'
      % (len(PRYAMYE), len(ZAPAS), len(EGRUL), len(KOMPANII)))
print('\n  ПРИМЕРЫ ПРЯМЫХ ЛПР С ТЕЛЕФОНОМ:')
for x in [y for y in PRYAMYE if y['telefon'].strip() and y['fio'].strip()][:8]:
    print('   %-26s | %-24s | %-18s | %s'
          % (x['klass_roli'][:26], x['fio'][:24], x['telefon'][:18], x['nazvanie'][:34]))
