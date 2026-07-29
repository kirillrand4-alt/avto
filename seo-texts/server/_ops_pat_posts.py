# -*- coding: utf-8 -*-
"""Все извлечённые должности раскрытия — проверка, что «0 технических» настоящий.

Ноль технических ЛПР мог быть дефектом классификатора, а не свойством
источника. Печатаем ВСЕ должности как есть и отдельно ищем в СЫРЫХ текстах
документов слова «главный инженер/энергетик/механик/технолог» — если их нет
и там, то ноль принадлежит источнику, а не разбору.
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
sys.argv = [sys.argv[0]]
import _ops_pat_disclosure as D   # noqa: E402

п = r'C:\sender\_ops\pat_disclosure.jsonl'
рек = []
for ln in io.open(п, encoding='utf-8', errors='replace'):
    try:
        рек.append(json.loads(ln))
    except Exception:  # noqa: BLE001
        pass

print('### ВСЕ ДОЛЖНОСТИ (%d записей)' % len(рек))
c = Counter()
for x in рек:
    for ч in (x.get('люди') or []):
        c[ч['должность']] += 1
        print('  %-46s | %-28s | тех=%s | %s'
              % (ч['должность'][:46], ч['фио'][:28], ч['тех'],
                 x['имя'][:24]))
print('### СВОДКА ДОЛЖНОСТЕЙ')
for д, n in c.most_common():
    print('  %2d  %s  (тех=%s)' % (n, д[:60], bool(D._ТЕХ.search(д))))

print('### ЕСТЬ ЛИ ТЕХНАРИ В СЫРЫХ ТЕКСТАХ ВООБЩЕ')
СЛ = re.compile(r'главн\w+\s+(?:инженер|энергетик|механик|технолог|конструктор)'
                r'|техническ\w+\s+директор', re.I)
for x in рек[:6]:
    попал = 0
    примеры = []
    for u in (x.get('источники') or [])[:4]:
        _u, t, _к = D.текст_дока(u)
        for m in list(СЛ.finditer(t or ''))[:2]:
            попал += 1
            примеры.append(re.sub(r'\s+', ' ', t[max(0, m.start() - 90):
                                                 m.end() + 110]))
    print('  %-40s упоминаний тех-должностей в документах: %d'
          % (x['имя'][:40], попал))
    for пр in примеры[:2]:
        print('      …%s…' % пр[:200])
print('POSTS ЗАВЕРШЕНА')
