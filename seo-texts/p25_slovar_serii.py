# -*- coding: utf-8 -*-
"""СЛОВАРЬ, часть 1: СЕРИИ из наших документов, с классом машины ИЗ ТЕКСТА, а не из головы.

Мой участок по согласованию — словарь целиком. 2-я дала вход со стороны каталога владельца
(63 бренда, 2 920 моделей — то, что он ПРОДАЁТ). Вторая половина словаря — то, что у завода
СТОИТ: отечественные серии ТВ/ЦК/К-/КТК/ЗИФ/ВЦ, которых в каталоге нет и взяться там неоткуда.

ГЛАВНОЕ РЕШЕНИЕ ПРИБОРА. Класс машины по серии я НЕ придумываю. «ТВ» это турбовоздуходувка,
а «К-250» центробежный — я это знаю, но знание надо доказать документом, иначе словарь
станет моим мнением. Поэтому для каждой серии собираю слова, стоящие РЯДОМ с ней в наших
документах, и класс ставлю по ним. Нет слов рядом — класс «не установлен», и так и пишется.

Это же даёт первую ось сортировки владельца (признак C: класс машины без модели).

ЗАСЛОНЫ, оплаченные сменой:
  * границы слова обязательны — «мост» ловился внутри «недвижимости», «АНО» внутри «Иванов»,
    «МЕТР» внутри «параметр»;
  * «турбокомпрессор» рядом с «кондиционер|трактор|сельхоз|автотранспорт|стартер» — НЕ наша
    машина: на первых восьми фактах ИНН 0245022178 это было 8 из 8 ложных «центробежных».

Только чтение. Печатает в КОНЦЕ.
"""
import collections
import json
import os
import re
import sqlite3

ISTOCHNIKI = [
    (r'C:\seostat\data\centrifugal.db', 'fact'),
    (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
    (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty'),
]

# Отечественные обозначения: буквенный префикс + цифры, через дефис или слитно.
SERIYA = re.compile(
    r'\b('
    r'(?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|ЗИФ|НВЭ|ВП|ВМ|ПКС|ЭК|АК|ТГ|ГПА|АДГ|ВК|КР|УКС|ВШ|КЦ|ТКА|Ц)'
    r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3}'
    r')\b', re.U)
KLASS = (
    ('центробежный', re.compile(r'центробежн', re.I)),
    ('турбокомпрессор', re.compile(r'турбокомпрессор|турбо-?компрессор', re.I)),
    ('воздуходувка', re.compile(r'воздуходув|турбовоздуходув|газодув', re.I)),
    ('нагнетатель', re.compile(r'нагнетател', re.I)),
    ('винтовой', re.compile(r'винтов', re.I)),
    ('поршневой', re.compile(r'поршнев', re.I)),
    ('ВРУ / разделение воздуха', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
    ('генератор азота/кислорода', re.compile(r'генератор\w*\s+(?:азота|кислорода)|'
                                             r'азотн\w+\s+станци|кислородн\w+\s+станци', re.I)),
    ('МКС / передвижная', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор|мобильн\w+\s+компрессор', re.I)),
    ('осушитель', re.compile(r'осушител', re.I)),
    ('компрессор без уточнения', re.compile(r'компрессор', re.I)),
)
CHUZHOE_RYADOM = re.compile(r'кондиционер|трактор|сельхоз|автотранспорт|стартер|'
                            r'John Deere|New Holland|Challenger|MacDon', re.I)

serii = collections.defaultdict(lambda: {'vsego': 0, 'klassy': collections.Counter(),
                                         'citaty': [], 'inn': set(), 'otbroshено': 0})
prosmotr = collections.Counter()

for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    except Exception:  # noqa: BLE001
        continue
    if not kol:
        cx.close()
        continue
    sel = ','.join('"%s"' % k for k in kol)
    pole_inn = 'inn' if 'inn' in kol else None
    for r in cx.execute('select %s from "%s"' % (sel, tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        prosmotr['%s.%s' % (os.path.basename(baza), tabl)] += 1
        for m in SERIYA.finditer(tekst):
            s = re.sub(r'\s+', '', m.group(1)).upper().replace(' ', '')
            okno = tekst[max(0, m.start() - 120):m.end() + 120]
            z = serii[s]
            if CHUZHOE_RYADOM.search(okno):
                z['otbroshено'] += 1
                continue
            z['vsego'] += 1
            for imya, rg in KLASS:
                if rg.search(okno):
                    z['klassy'][imya] += 1
                    break
            if pole_inn and str(d.get(pole_inn) or '').strip():
                z['inn'].add(str(d[pole_inn]).strip())
            if len(z['citaty']) < 2:
                z['citaty'].append(re.sub(r'\s+', ' ', okno)[:160])
    cx.close()

# --- проба: серии, которые ОБЯЗАНЫ быть найдены и классифицированы ------------------
PROBA = [('ТВ-80-1', 'воздуходувка'), ('ЦК-135', 'центробежный'), ('КТК-12', None),
         ('ТВ-200-1', 'воздуходувка')]
provaly = []
for s, zhdem in PROBA:
    k = s.replace(' ', '').upper()
    if k not in serii:
        provaly.append('НЕ НАЙДЕНА серия %s' % s)
    elif zhdem:
        top = serii[k]['klassy'].most_common(1)
        if not top or top[0][0] != zhdem:
            provaly.append('%s: ждали «%s», вышло «%s»'
                           % (s, zhdem, top[0][0] if top else 'класс не установлен'))

itog = {}
for s, z in serii.items():
    if z['vsego'] < 2:
        continue
    top = z['klassy'].most_common(1)
    itog[s] = {'встреч': z['vsego'], 'ИНН': len(z['inn']),
               'класс': top[0][0] if top else 'не установлен',
               'класс_голосов': top[0][1] if top else 0,
               'отброшено_как_трактор': z['otbroshено'],
               'цитата': z['citaty'][0] if z['citaty'] else ''}

print('\n\n########## ДВАДЦАТЬ САМЫХ ЧАСТЫХ СЕРИЙ, ГЛАЗАМИ')
for s, z in sorted(itog.items(), key=lambda x: -x[1]['встреч'])[:20]:
    print('\n  %-14s встреч %5d  ИНН %4d  класс: %s (голосов %d)'
          % (s, z['встреч'], z['ИНН'], z['класс'], z['класс_голосов']))
    print('      %s' % z['цитата'][:150])

print('\n\n########## ПРОБА')
for p in provaly:
    print('  ПРОВАЛ: %s' % p)
print('  провалов %d из %d' % (len(provaly), len(PROBA)))

print('\n########## ЧИСЛА')
for k, v in prosmotr.most_common():
    print('  просмотрено %-34s %7d' % (k, v))
print('  серий найдено (встреч >= 2)      %6d' % len(itog))
kl = collections.Counter(z['класс'] for z in itog.values())
for k, v in kl.most_common():
    print('     %-30s %5d' % (k, v))
print('  отброшено как трактор/кондиционер: %d'
      % sum(z['отброшено_как_трактор'] for z in itog.values()))
print('ИТОГ ' + json.dumps({'серий': len(itog), 'провалов': len(provaly),
                            'классы': dict(kl)}, ensure_ascii=False))
