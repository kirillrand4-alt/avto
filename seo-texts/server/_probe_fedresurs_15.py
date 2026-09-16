# -*- coding: utf-8 -*-
"""Проба 15: реальная отдача источника. Берём 150 ИНН нашей базы по ICP-ОКВЭД,
окно 90 дней, без карточек (2 запроса на компанию) — считаем, сколько компаний
дают капекс-сообщение и какие типы."""
import io, sys, json, time
from collections import Counter

sys.path.insert(0, r'C:\sender\_tmp')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import collector_fedresurs as F  # noqa: E402

ICP = ['10', '11', '20', '21', '22', '23', '24', '25', '27', '28', '35', '36', '38', '41', '42']
kand = F.inn_iz_bazy(okved=ICP, limit=150, offset=300)
print('кандидатов: %d' % len(kand))

t0 = time.time()
got = F.col_fedresurs(days=90, max_items=4000, inns=[i for i, _ in kand],
                      pause=0.25, detali=False, log=lambda s: print('  [лог] ' + s))
dt = time.time() - t0
s = F.col_fedresurs.summary
print('\n=== СВОДКА за %.0fс ===' % dt)
for k, v in sorted(s.items()):
    print('  %-42s %s' % (k, v))
inn_s = {it['inn'] for it in got}
print('  item-ов: %d по %d компаниям' % (len(got), len(inn_s)))
print('  запросов примерно: %d (2 на компанию)' % (2 * len(kand)))
print('  темп: %.1f компаний/мин' % (60.0 * len(kand) / max(dt, 1)))

print('\n=== ТИПЫ ===')
for k, v in Counter(it['msg_type'] for it in got).most_common():
    print('  %-40s %s' % (k, v))
print('\n=== СТАДИИ ===')
print('  %s' % dict(Counter(it['stage'] for it in got)))
print('\n=== ПРИМЕРЫ ===')
for it in got[:14]:
    print('  %s %-11s %-38s %s' % (it['pubDate'], it['inn'], (it['company_name'] or '')[:38],
                                   it['msg_type']))
print('\n=== ОЦЕНКА НА ВСЮ БАЗУ ===')
if kand:
    dolya = len(inn_s) / float(len(kand))
    print('  доля компаний с капекс-сообщением за 90 дней: %.1f%%' % (100 * dolya))
    print('  при 169 704 компаниях это ~%.0f компаний и ~%.0f сообщений за окно'
          % (169704 * dolya, 169704 * len(got) / float(len(kand))))
    print('  полный обход базы: ~%.0f запросов, ~%.1f часов при паузе 0.25с'
          % (2 * 169704, 2 * 169704 * 0.30 / 3600.0))
print('\n==== КОНЕЦ ПРОБЫ 15 ====')
