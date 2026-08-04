# -*- coding: utf-8 -*-
"""Дубли людей в p25.db: клонированная схема не держит уникальность.

ЧТО СЛУЧИЛОСЬ. При заливке 206 строк оп отчитался «завести 86, только
наблюдение 120», а `person` вырос на 206. Значит `INSERT OR IGNORE` ничего не
проигнорировал: в таблице НЕТ уникального индекса по (ИНН, человек). Я
клонировал DDL боевой базы и унаследовал её отсутствие — «схема совпадает по
построению» защитило от расхождения имён, но не от этого.

ЧИНЮ В ТРИ ШАГА, и порядок важен:
  1. посчитать дубли (не поверить, а увидеть);
  2. оставить по одной строке на (ИНН, человек), выбирая САМУЮ ПОЛНУЮ —
     с телефоном, потом с должностью, потом с датой подтверждения;
  3. поставить уникальный индекс, чтобы это не повторилось.

Чистка идёт по rowid и НЕ трогает contact_source: наблюдения — это история,
у них своя уникальность (ИНН + значение + ссылка + дата), и дублей там нет.

Запуск: python p25_dubli_lyudey.py [--apply]
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict

P25 = r'C:\seostat\data\p25.db'
ПРИМЕНИТЬ = '--apply' in sys.argv

цб = sqlite3.connect(P25, timeout=30)
индексы = [r[0] for r in цб.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='person'")]
print('индексы person:', индексы or 'НЕТ НИ ОДНОГО')

группы = defaultdict(list)
for rid, инн, ч, тел, поз, дата in цб.execute(
        "SELECT rowid, inn, COALESCE(person,''), COALESCE(phone,''), "
        "COALESCE(position,''), COALESCE(data_podtverzhdeniya,'') FROM person"):
    группы[(str(инн), ' '.join(str(ч).split()).casefold())].append(
        (rid, тел, поз, дата))

с = Counter()
к_удалению = []
for ключ, строки in группы.items():
    с['разных людей'] += 1
    if len(строки) < 2:
        continue
    с['людей с дублями'] += 1
    с['лишних строк'] += len(строки) - 1
    # САМАЯ ПОЛНАЯ ВЫЖИВАЕТ: телефон важнее должности, должность важнее даты
    строки.sort(key=lambda с_: (bool(с_[1]), bool(с_[2]), bool(с_[3]), -с_[0]),
                reverse=True)
    for rid, _t, _p, _d in строки[1:]:
        к_удалению.append(rid)

всего = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
print(json.dumps(dict(с), ensure_ascii=False))
print(f'строк person сейчас {всего}, к удалению {len(к_удалению)}, '
      f'останется {всего - len(к_удалению)}')

# и то же по contact: там уникальность тоже могла не приехать
гк = defaultdict(list)
for rid, инн, вид, зн, ч in цб.execute(
        "SELECT rowid, inn, COALESCE(kind,''), COALESCE(value,''), "
        "COALESCE(person,'') FROM contact"):
    гк[(str(инн), вид, зн, ' '.join(str(ч).split()).casefold())].append(rid)
лишних_к = sum(len(v) - 1 for v in гк.values() if len(v) > 1)
всего_к = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
print(f'строк contact сейчас {всего_к}, лишних дублей {лишних_к}')

if not ПРИМЕНИТЬ:
    print('\nСУХОЙ ПРОГОН, ничего не удалено')
    цб.close()
    raise SystemExit(0)

до = цб.total_changes
for i in range(0, len(к_удалению), 500):
    кусок = к_удалению[i:i + 500]
    цб.execute(f"DELETE FROM person WHERE rowid IN ({','.join('?' * len(кусок))})",
               кусок)
# contact
к_уд_к = []
for v in гк.values():
    if len(v) > 1:
        к_уд_к.extend(sorted(v)[1:])
for i in range(0, len(к_уд_к), 500):
    кусок = к_уд_к[i:i + 500]
    цб.execute(f"DELETE FROM contact WHERE rowid IN ({','.join('?' * len(кусок))})",
               кусок)
цб.commit()
удалено = цб.total_changes - до

# ЗАСЛОН НА БУДУЩЕЕ: без него чистка повторится после каждой заливки
for sql in (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_person ON person(inn, person)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_contact ON contact("
    "inn, kind, value, COALESCE(person,''))",
):
    try:
        цб.execute(sql)
        print('индекс поставлен:', sql.split(' ON ')[0].split()[-1])
    except Exception as ex:  # noqa: BLE001
        print('индекс НЕ поставлен:', str(ex)[:110])
цб.commit()
стало_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
стало_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
разных = цб.execute('SELECT COUNT(DISTINCT inn || "|" || person) FROM person').fetchone()[0]
цб.close()
print(f'\nудалено строк: {удалено}')
print(f'person: {стало_p} (разных людей {разных}) | contact: {стало_c}')
