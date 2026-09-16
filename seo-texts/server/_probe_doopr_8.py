# -*- coding: utf-8 -*-
"""Проба 8: профиль безымянных событий — типы, стадии, применимость путей 2/4/6.
Только чтение jsonl. Итог печатается ПОСЛЕДНИМ."""
import json
import re
from collections import Counter

JS = r'C:\sender\server\news_stream.jsonl'
recs = []
for line in open(JS, encoding='utf-8', errors='replace'):
    line = line.strip()
    if line:
        try:
            recs.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
anon = [r for r in recs if not (r.get('company') or '').strip()]
named = [r for r in recs if (r.get('company') or '').strip()]

tipy = Counter(r.get('event_type') for r in anon)
STADII = {
    '1 проект/анонс': r'планиру|намерен|построят|создадут|проект\w* документац|соглашени|инвестир\w+ будет|заявк',
    '2 стройка': r'строительство|строят|возвод|заложили|котлован|стройплощад',
    '3 пуск': r'запуст|открыл|введ\w+ в эксплуатац|начал\w* выпуск|первая продукц',
    '4 расширение': r'расшир|модерниз|увелич\w+ мощност|вторая очеред',
}
stadii = Counter()
for r in anon:
    t = ' '.join([r.get('title') or '', r.get('what') or ''])
    nash = [k for k, p in STADII.items() if re.search(p, t, re.I)]
    stadii[nash[0] if nash else '5 не определена'] += 1

s_date = sum(1 for r in anon if (r.get('published') or '').strip())
s_reg = sum(1 for r in anon if (r.get('region') or '').strip())
s_sum = sum(1 for r in anon if (r.get('sum') or '').strip())
# путь 2 (ЕГРЗ) применим к капстрою: стройка/проект нового объекта
egrz_ok = sum(1 for r in anon
              if re.search(r'строительств|построят|возвед|заложил|проектн\w+ документац|экспертиз',
                           ' '.join([r.get('title') or '', r.get('what') or '']), re.I))
# путь 4 (Федресурс): у события названа сумма или речь о сделке/покупке актива
fedr_ok = sum(1 for r in anon
              if re.search(r'\d[\d\s.,]*(млн|млрд)|сделк|прио?брет|выкуп|актив|доля в',
                           ' '.join([r.get('title') or '', r.get('what') or '']), re.I))

print()
print('==================== ИТОГ (главное) ====================')
print('безымянных: %d (из %d записей потока, %.0f%%)'
      % (len(anon), len(recs), 100.0 * len(anon) / len(recs)))
print('типы событий у безымянных:', dict(tipy.most_common(8)))
print('стадии у безымянных:', dict(stadii.most_common()))
print('у безымянных заполнено: дата %d (%.0f%%), регион %d (%.0f%%), сумма %d (%.0f%%)'
      % (s_date, 100.0 * s_date / len(anon), s_reg, 100.0 * s_reg / len(anon),
         s_sum, 100.0 * s_sum / len(anon)))
print('применимость путей: ЕГРЗ (капстрой в тексте) %d (%.0f%%); Федресурс (сумма/сделка) %d (%.0f%%)'
      % (egrz_ok, 100.0 * egrz_ok / len(anon), fedr_ok, 100.0 * fedr_ok / len(anon)))
print('для сравнения — стадии у ИМЕНОВАННЫХ: %s'
      % dict(Counter(next((k for k, p in STADII.items()
                           if re.search(p, ' '.join([r.get('title') or '', r.get('what') or '']), re.I)),
                          '5 не определена') for r in named).most_common()))
