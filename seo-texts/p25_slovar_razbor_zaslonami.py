# -*- coding: utf-8 -*-
"""СЛОВАРЬ: что в нём стоит, что снимают заслоны и умеет ли он отличать серию от не-серии.

Живой файл: `PARK-SLOVAR-EDINYY.csv` (скачивается с дропа перед замером, отметка времени
печатается — иначе число окажется из вчерашней копии).

ПОЧЕМУ ЗАМЕР ПЕРЕПИСАН. Первый счёт дал «с доказанным видом машины 3 906 из 3 906, 100 %».
Сто процентов — повод проверить прибор, и прибор действительно врал: я считала «поле
`vid_mashiny` не пустое», а в 147 строках там стоит буквально «не установлен». Кроме того
«назван» и «доказан» — разные вещи: у 2 920 строк источник это каталог владельца (его
собственный товар, не доказательство парка), и только у части стоит ссылка на документ.

Здесь считается раздельно:

    вид НАЗВАН        поле заполнено и это не «не установлен»
    вид ДОКАЗАН       к строке приложена ссылка (документ ЭПБ, закупка) — её можно открыть
    источник каталог  собственный каталог владельца: для парка это не доказательство

ЗАСЛОНЫ прогоняются по ВСЕМУ словарю заново — не по журналу, а по живым строкам:
позиция/зав.№, чужая машина, пометка «машина лишь упомянута», технологический номер.

ПРОБА НА РАЗЛИЧЕНИЕ. К настоящим обозначениям подмешиваются выдуманные и заведомо не-серии:
`ЩВ-999`, `поз. 12`, `зав. № 4471`, `насос НМ-1250`, `вентилятор ВДН-18`, `Ми-8`. Если мерка
пропустит их как серии — она не различает, и числам словаря верить нельзя. Печатается
«провалов столько-то из стольких-то».

Числа в КОНЦЕ.
"""
import collections
import csv
import io
import os
import re
import time

SCRATCH = os.environ.get('P25_SCRATCH', '.')
SLOVAR = os.path.join(SCRATCH, 'PARK-SLOVAR-EDINYY.csv')
SERIYA = re.compile(
    r'\b((?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|ЗИФ|НВЭ|ВП|ВМ|ПКС|ЭК|АК|ТГ|ГПА|АДГ|ВК|КР|УКС|ВШ|ТКА|Ц)'
    r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3})\b', re.U)
CHUZH = re.compile(r'вентилятор|дымосос|\bнасос\w*\b|градирн|кондиционер|трактор|сельхоз|'
                   r'автотранспорт|стартер|автомат\w*\s+выключател|\bIP\d\d\b|'
                   r'золотоизвлекательн|турбогенератор|турбоагрегат|турбовальн|\bМи-8\b|'
                   r'адсорбер|абсорбер|паропровод|\bЦВД\b|\bЦСД\b', re.I)
POZ = re.compile(r'^\s*(поз\.?|позици\w*|№|техн\.?\s*№|зав\.?\s*№|инв\.?\s*№)\s*[\d\-/]*\s*$',
                 re.I)
POMETKA = re.compile(r'машина\s+лишь\s+упомянута|не\s+применимо|объект\s*[—-]\s*трубопровод',
                     re.I)
SADOVAYA = re.compile(r'садов|бытов|ранцев|листь|пылесос|снегоубор|опрыскиват', re.I)
VYDUMKI = ['ЩВ-999', 'поз. 12', 'зав. № 4471', 'насос НМ-1250', 'вентилятор ВДН-18',
           'Ми-8', 'инв. № 100711', 'кондиционер BK-2000', 'ЩВАРЦКОПФЕРЪ-5',
           'адсорбер А-12']

print('живой файл: %s' % SLOVAR)
if os.path.exists(SLOVAR):
    print('отметка времени файла: %s UTC'
          % time.strftime('%d.%m %H:%M', time.gmtime(os.path.getmtime(SLOVAR))))
else:
    raise SystemExit('файла нет — замер невозможен, это не «ноль строк»')

stroki = []
with io.open(SLOVAR, encoding='utf-8-sig') as f:
    for r in csv.DictReader(f, delimiter=';'):
        stroki.append(r)

sch = collections.Counter()
zaslony = collections.Counter()
primery = collections.defaultdict(list)
for r in stroki:
    ob = (r.get('oboznachenie') or '').strip()
    vid = (r.get('vid_mashiny') or '').strip()
    ist = (r.get('istochnik') or '')
    ssyl = (r.get('ssylok') or '').strip()
    sch['строк всего'] += 1
    if vid and vid.lower() != 'не установлен':
        sch['вид НАЗВАН'] += 1
    else:
        sch['вид не установлен'] += 1
    if ssyl:
        sch['вид ДОКАЗАН ссылкой'] += 1
    if 'каталог prokompressor' in ist:
        sch['источник — каталог владельца (для парка не доказательство)'] += 1
    # заслоны заново, по живой строке
    if POZ.match(ob):
        zaslony['позиция / зав. № / инв. №'] += 1
        primery['позиция / зав. № / инв. №'].append(ob)
    elif CHUZH.search(ob) or CHUZH.search(ist[:200]):
        zaslony['чужая машина / чужой предмет'] += 1
        primery['чужая машина / чужой предмет'].append(ob)
    elif POMETKA.search(ist):
        zaslony['пометка: машина лишь упомянута'] += 1
        primery['пометка: машина лишь упомянута'].append(ob)
    elif SADOVAYA.search(ob) or SADOVAYA.search(ist[:200]):
        zaslony['садовая техника'] += 1
        primery['садовая техника'].append(ob)

# ПРОБА НА РАЗЛИЧЕНИЕ
nastoyashchie = [(r.get('oboznachenie') or '').strip() for r in stroki
                 if (r.get('vid_zapisi') or '').startswith('серия')]
proshli_nast = [o for o in nastoyashchie if SERIYA.search(o)]
provaly = []
for v in VYDUMKI:
    est_seriya = bool(SERIYA.search(v))
    otsek = bool(POZ.match(v) or CHUZH.search(v))
    if est_seriya and not otsek:
        provaly.append(v)

print('\n\n########## ЧТО СТОИТ В СЛОВАРЕ')
for k, v in sch.most_common():
    print('  %-56s %5d' % (k[:56], v))
print('\n########## ЧТО СНИМАЮТ ЗАСЛОНЫ (по живым строкам, заново)')
if not zaslony:
    print('  ни одна строка не снята — словарь уже прошёл заслоны прежними прогонами')
for k, v in zaslony.most_common():
    print('  %-46s %4d   например: %s' % (k[:46], v, ', '.join(primery[k][:2])[:44]))
print('\n########## ПРОБА НА РАЗЛИЧЕНИЕ')
print('  настоящих серий в словаре            %5d' % len(nastoyashchie))
print('  из них мерка узнаёт как серию        %5d' % len(proshli_nast))
print('  подмешано выдумок и не-серий         %5d' % len(VYDUMKI))
print('  ПРОВАЛОВ (выдумка принята за серию)  %5d из %d' % (len(provaly), len(VYDUMKI)))
if provaly:
    print('     провалились: %s' % ', '.join(provaly))
print('ИТОГ ' + str({'строк': sch['строк всего'], 'вид назван': sch['вид НАЗВАН'],
                     'доказан ссылкой': sch['вид ДОКАЗАН ссылкой'],
                     'узнаёт серий': '%d из %d' % (len(proshli_nast), len(nastoyashchie)),
                     'провалов': '%d из %d' % (len(provaly), len(VYDUMKI))}))
