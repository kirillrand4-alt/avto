# -*- coding: utf-8 -*-
"""Приём ОКВЭД от 2-й сессии (страница деятельности checko).

Допущение «первый код на странице = ОСНОВНОЙ ОКВЭД» проверено, а не принято на веру:
у 361 предприятия ОКВЭД уже был из другого источника (реквизиты, база обзвона), и первый
код 2-й сессии совпал **361 раз из 361**. Сравнивал только КОД: моё поле иногда хранит
«код + название» одной строкой, и сравнение целых строк сначала объявило 81 расхождение,
которого нет. Пересчитал по коду — расхождений ноль.

Пишем: основной код в `finansy.okved`, ПОЛНЫЙ список в новую колонку `okved_vse`
(у предприятия их бывает семь и больше — по одному коду видно не всё), провенанс в
`okved_otkuda` вместе со ссылкой на страницу, где это видно.

Запуск: python3 park_vlit_okved_2s.py [файл.jsonl]
"""
import collections, json, os, re, sqlite3, sys

D = os.path.dirname(os.path.abspath(__file__))
FAYL = os.path.join(D, sys.argv[1] if len(sys.argv) > 1 else 'PARK-OKVED-2S.jsonl')
p = sqlite3.connect(os.path.join(D, 'park.db'))
cur = p.cursor()

if 'okved_vse' not in [r[1] for r in cur.execute('pragma table_info(finansy)')]:
    cur.execute('alter table finansy add column okved_vse text')
    print('добавлена колонка finansy.okved_vse')

park = {r[0] for r in cur.execute('select inn from predpriyatie')}
est = {r[0] for r in cur.execute("select inn from finansy where coalesce(okved,'')<>''")}


def kod(s):
    m = re.match(r'\s*(\d{2}(?:\.\d{1,2}){0,3})', s or '')
    return m.group(1) if m else ''


pri = collections.Counter()
vs = zapis = spisok = 0
for ln in open(FAYL, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    try:
        x = json.loads(ln)
    except Exception:
        pri['строка не разобралась'] += 1
        continue
    vs += 1
    inn = str(x.get('inn') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        pri['ИНН не разобран'] += 1
        continue
    if inn not in park:
        pri['предприятия нет в парке'] += 1
        continue
    kody = [kod(k) for k in (x.get('okved_kody') or []) if kod(k)]
    if not kody:
        pri['кодов в записи нет'] += 1
        continue
    ssylka = (x.get('ssylka') or '').strip()
    otkuda = 'checko (2-я сессия), страница деятельности%s' % ((': ' + ssylka) if ssylka else '')
    vse = ' | '.join((x.get('okved_s_imenami') or kody))[:1200]
    cur.execute("insert or ignore into finansy(inn, ts) values (?, datetime('now'))", (inn,))
    cur.execute("update finansy set okved_vse=? where inn=?", (vse, inn))
    spisok += 1
    if inn in est:
        pri['основной ОКВЭД уже был — перезаписывать не стал, список дополнил'] += 1
        continue
    cur.execute("update finansy set okved=?, okved_otkuda=? where inn=?", (kody[0], otkuda, inn))
    zapis += 1

p.commit()
print('строк на входе %d' % vs)
print('  основной ОКВЭД записан ... %d предприятиям' % zapis)
print('  полный список записан .... %d' % spisok)
print('  пропуски:', dict(pri.most_common(6)))
q = lambda s: cur.execute(s).fetchone()[0]
print('\n=== ПО БАЗЕ ===')
print('  ОКВЭД у ................. %d предприятий парка' % q(
    "select count(*) from finansy f join predpriyatie e on e.inn=f.inn where coalesce(f.okved,'')<>''"))
print('  список кодов у .......... %d' % q(
    "select count(*) from finansy where coalesce(okved_vse,'')<>''"))
p.close()
