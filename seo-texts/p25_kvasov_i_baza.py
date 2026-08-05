# -*- coding: utf-8 -*-
"""Где именно живёт метка «личный» на московском городском: файлы чисты, значит смотрим базы.

Проход по всем выкладкам дропа дал НОЛЬ случаев «городской помечен личным» — ни у меня,
ни у 1-й, ни у 2-й сессии. Значит либо метка стоит не в файлах, а в БАЗЕ, из которой
считается мера, либо речь о конкретной строке, которую надо найти поимённо.

Прибор делает две вещи:
  1) ищет номер Квасова (7 495 926-14-20) везде — в файлах и в базах — и печатает,
     каким видом он назван в каждом месте;
  2) проходит таблицы контактов обеих баз тем же правилом «личный начинается на 79».

Базы важнее файлов: главная мера ТЗ считается по ним, и ошибка там дороже.
"""
import collections
import csv
import glob
import json
import os
import re
import sqlite3

D = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 8)
ISKOMYY = '74959261420'


def cifry(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


print('=== 1. НОМЕР КВАСОВА В ФАЙЛАХ')
nashli = 0
for p in sorted(glob.glob(os.path.join(D, '*.csv'))):
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = csv.DictReader(f, delimiter=';')
            polya = rd.fieldnames or []
            for r in rd:
                if not any(cifry(r.get(k)) == ISKOMYY for k in polya if k):
                    continue
                nashli += 1
                if nashli <= 8:
                    interes = {k: v for k, v in r.items()
                               if k and v and re.search(
                                   r'vid|tip|chelovek|fio|dolzh|telefon|nomer|znach|lichn',
                                   k, re.I)}
                    print('  %s' % os.path.basename(p))
                    print('    %s' % json.dumps({k: str(v)[:44] for k, v in interes.items()},
                                                ensure_ascii=False)[:420])
    except Exception:  # noqa: BLE001
        continue
print('  найдено строк: %d' % nashli)

print('=== 2. МЕТКА «ЛИЧНЫЙ» НА ГОРОДСКОМ В БАЗАХ')
for imya, put in (('p25', 'file:C:/seostat/data/p25.db?mode=ro'),
                  ('centrifugal', 'file:C:/seostat/data/centrifugal.db?mode=ro')):
    try:
        b = sqlite3.connect(put, uri=True)
        tablicy = [t for (t,) in b.execute("select name from sqlite_master where type='table'")]
    except Exception as e:  # noqa: BLE001
        print('  %s: %s' % (imya, e))
        continue
    sch = collections.Counter()
    primery = []
    for t in tablicy:
        try:
            polya = [r[1] for r in b.execute('pragma table_info(%s)' % t)]
        except Exception:  # noqa: BLE001
            continue
        # Колонка со значением контакта и колонка с его видом — берутся из схемы.
        kn = [x for x in polya if re.search(r'value|znach|telefon|phone|nomer|contact', x, re.I)]
        kv = [x for x in polya if re.search(r'\btip\b|vid|kind|type|lichn|priznak', x, re.I)]
        if not (kn and kv):
            continue
        try:
            for r in b.execute('select %s from %s' % (','.join(polya), t)):
                z = dict(zip(polya, r))
                vid = ' '.join(str(z.get(x) or '') for x in kv)
                if not re.search(r'личн|мобильн|сотов', vid, re.I):
                    continue
                if re.search(r'не\s+личн|общий|не_личн', vid, re.I):
                    continue
                for k in kn:
                    c = cifry(z.get(k))
                    if not c:
                        continue
                    if c.startswith('79'):
                        sch['%s.%s верно' % (t, k)] += 1
                    else:
                        sch['%s.%s ОШИБКА: городской помечен личным' % (t, k)] += 1
                        if len(primery) < 8:
                            primery.append((t, k, c, vid[:40]))
        except Exception:  # noqa: BLE001
            continue
    print('  --- %s' % imya)
    for t, k, c, vid in primery:
        print('     %s.%s  %s  вид: %s' % (t, k, c, vid))
    for k, v in sorted(sch.items()):
        print('     REC %s\t%d' % (k, v))

print('ИТОГ ' + json.dumps({'строк с номером Квасова в файлах': nashli}, ensure_ascii=False))
