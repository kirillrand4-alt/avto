# -*- coding: utf-8 -*-
"""Проба 17: качество потока. Сколько из лизинга/залога — ДЕЙСТВИТЕЛЬНО наша техника,
а сколько автопарк и дорожная техника. Считаем по предмету из карточки."""
import io, sys, time
from collections import Counter

sys.path.insert(0, r'C:\sender\_tmp')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import collector_fedresurs as F  # noqa: E402

ICP = ['10', '11', '20', '21', '22', '23', '24', '25', '27', '28', '35', '36', '38', '41', '42']
kand = F.inn_iz_bazy(okved=ICP, limit=150, offset=300)
t0 = time.time()
got = F.col_fedresurs(days=90, max_items=90, inns=[i for i, _ in kand],
                      tipy=['FinancialLeaseContract2', 'ChangeFinancialLeaseContract2',
                            'CreationRightOfPledge2'],
                      pause=0.25, detali=True, log=lambda s: print('  [лог] ' + s))
print('\nвзято %d сообщений за %.0fс' % (len(got), time.time() - t0))

hot = Counter(it.get('hotness') for it in got)
print('\n=== hotness (5 = наша техника, 4 = промышленная, 2 = автопарк/дорожная) ===')
for k in sorted(hot, reverse=True):
    print('  hotness %s: %d (%.0f%%)' % (k, hot[k], 100.0 * hot[k] / max(len(got), 1)))
print('  с суммой в карточке: %d' % sum(1 for it in got if it['sum']))

print('\n=== НАШИ (hotness 5) ===')
n = 0
for it in got:
    if it.get('hotness') == 5:
        n += 1
        print('  %s %-11s %s' % (it['pubDate'], it['inn'], it['title'][:150]))
print('  всего: %d' % n)

print('\n=== ПРОМЫШЛЕННЫЕ (hotness 4) — соседний повод ===')
n = 0
for it in got:
    if it.get('hotness') == 4:
        n += 1
        if n <= 12:
            print('  %s %-11s %s' % (it['pubDate'], it['inn'], it['title'][:150]))
print('  всего: %d' % n)

print('\n=== ШУМ (hotness 2) — первые 8 для понимания ===')
n = 0
for it in got:
    if it.get('hotness') == 2:
        n += 1
        if n <= 8:
            print('  %s %-11s %s' % (it['pubDate'], it['inn'], it['title'][:130]))
print('  всего: %d' % n)
print('\n==== КОНЕЦ ПРОБЫ 17 ====')
