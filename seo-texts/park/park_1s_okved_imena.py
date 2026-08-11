# -*- coding: utf-8 -*-
"""Подписывает коды ОКВЭД названиями. Владелец: «почему основной не подписан».

В карточке предприятия «Все виды деятельности» показывали 21 код с названиями, а «Основной
ОКВЭД» — голый `35.11.3`. Смотрится как сбой панели, но дело в данных: 2-я сессия отдала
основной код отдельным полем БЕЗ названия (`okved='35.11.3'`), а названия пришли только в
списке всех кодов — и именно для основного там пусто (`okved_vse='10.51 '` — код и пробел).

Так голыми остались **1 687 основных кодов из 2 635**.

Чинится не догадками, а справочником. Официальный ОКВЭД-2 (2 814 кодов) уже лежал в
репозитории — `seo-texts/sender-data/okved-names.json`, им подписывает коды рассыльщик. Я его
не искал, потому что чинил ОКВЭД внутри задачи про парк и не посмотрел, чем закрыт тот же
вопрос в соседнем проекте того же репозитория.

Порядок источников имени — от твёрдого к мягкому, и каждый помечается в базе:

    1. `классификатор ОКВЭД-2`   — точное название кода из официального справочника;
    2. `из базы: <код>`          — название, встреченное у других предприятий с этим же кодом
                                   (беру самое длинное: короткие — обрезки от 110-значного
                                   поля, «Произ» вместо «Производство электроэнергии»);
    3. `название родительского <код>` — если самого кода нигде нет, подписываю разделом
                                   выше и ГОВОРЮ об этом, а не выдаю за точное имя.

Ссылку-доказательство на вид деятельности не выдумываю: она есть у 588 предприятий (страница
деятельности checko от 2-й сессии), у остальных источник — карточки обогащения и база
обзвона, и там ссылки нет. Строить адрес по ИНН нельзя: это тот самый класс поддельных
ссылок, которых я уже пометил 2 066 штук.

Запуск: python3 park_1s_okved_imena.py [--pisat]
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
PISAT = '--pisat' in sys.argv
KLASSIFIKATOR = '/home/user/avto/seo-texts/sender-data/okved-names.json'


def imena_iz_bazy(c):
    """Названия, уже встреченные в базе: код -> самое длинное (короткие — обрезки поля)."""
    luchshee = defaultdict(str)
    for (vse,) in c.execute("select okved_vse from finansy where coalesce(okved_vse,'')<>''"):
        for kus in vse.split('|'):
            m = re.match(r'^(\d{2}(?:\.\d{1,2}){0,3})\s+(.{4,})$', kus.strip())
            if m and len(m.group(2)) > len(luchshee[m.group(1)]):
                luchshee[m.group(1)] = m.group(2).strip()
    return luchshee


def nayti_imya(kod, klass, iz_bazy):
    """-> (название, чем подписано). Пустое название — если не нашлось ничего."""
    if kod in klass:
        return klass[kod], 'классификатор ОКВЭД-2'
    if kod in iz_bazy:
        return iz_bazy[kod], 'из базы: ' + kod
    rod = kod
    while '.' in rod:
        rod = rod.rsplit('.', 1)[0]
        if rod in klass:
            return klass[rod], 'название родительского ' + rod
        if rod in iz_bazy:
            return iz_bazy[rod], 'название родительского ' + rod
    return '', ''


klass = json.load(open(KLASSIFIKATOR, encoding='utf-8'))
p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=180)
c, c2 = p.cursor(), p.cursor()
est = [r[1] for r in c.execute('pragma table_info(finansy)')]
if PISAT:
    for kol in ('okved_imya', 'okved_imya_otkuda', 'okved_vse_imena'):
        if kol not in est:
            c.execute('alter table finansy add column %s text' % kol)

iz_bazy = imena_iz_bazy(c)
print('справочник: классификатор ОКВЭД-2 %d кодов, из базы ещё %d' % (len(klass), len(iz_bazy)))

itog = {'подписан основной': 0, 'уже был с названием': 0, 'не нашлось имени': 0,
        'кодов в списках подписано': 0}
otkuda = defaultdict(int)
nikak = set()
for inn, ok, vse in c.execute("""select inn, coalesce(okved,''), coalesce(okved_vse,'')
                                   from finansy where coalesce(okved,'')<>''"""):
    kod = ok.strip().split()[0] if ok.strip() else ''
    if not re.fullmatch(r'\d{2}(\.\d{1,2}){0,3}', kod):
        continue
    imya, chem = nayti_imya(kod, klass, iz_bazy)
    if re.match(r'^\d[\d.]*\s+\S', ok.strip()):
        itog['уже был с названием'] += 1
        imya = imya or ok.strip().split(None, 1)[1]
        chem = chem or 'пришло с кодом'
    elif imya:
        itog['подписан основной'] += 1
    else:
        itog['не нашлось имени'] += 1
        nikak.add(kod)
    otkuda[chem or '(не нашлось)'] += 1
    # весь список кодов тоже подписываем: в карточке он показан целиком
    kody_spisok = []
    for kus in (vse.split('|') if vse else [kod]):
        m = re.match(r'^(\d{2}(?:\.\d{1,2}){0,3})\b\s*(.*)$', kus.strip())
        if not m:
            continue
        k, ostatok = m.group(1), m.group(2).strip()
        if len(ostatok) < 4:
            n, _ = nayti_imya(k, klass, iz_bazy)
            if n:
                ostatok = n
                itog['кодов в списках подписано'] += 1
        kody_spisok.append(('%s %s' % (k, ostatok)).strip())
    if PISAT:
        c2.execute("""update finansy set okved_imya=?, okved_imya_otkuda=?, okved_vse_imena=?
                       where inn=?""", (imya, chem, ' | '.join(kody_spisok), inn))

for k, v in itog.items():
    print('  %-28s %d' % (k, v))
print()
print('чем подписан основной код:')
for k, v in sorted(otkuda.items(), key=lambda x: -x[1]):
    print('   %-40s %d' % (k[:40], v))
if nikak:
    print()
    print('коды, которым имени не нашлось нигде (%d): %s'
          % (len(nikak), ', '.join(sorted(nikak)[:20])))
if not PISAT:
    print()
    print('сухой прогон, база не тронута; писать — с ключом --pisat')
    p.rollback()
    p.close()
    raise SystemExit
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ОКВЭД: коды подписаны названиями',
           itog['подписан основной'] + itog['уже был с названием'], itog['подписан основной'],
           itog['не нашлось имени'],
           'классификатор ОКВЭД-2 лежал в репозитории — им подписывает коды рассыльщик'))
p.commit()
print()
print('с названием основного ОКВЭД: %d из %d'
      % (c.execute("select count(*) from finansy where coalesce(okved_imya,'')<>''").fetchone()[0],
         c.execute("select count(*) from finansy where coalesce(okved,'')<>''").fetchone()[0]))
p.close()
