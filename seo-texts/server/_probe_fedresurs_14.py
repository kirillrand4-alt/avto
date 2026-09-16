# -*- coding: utf-8 -*-
"""Проба 14: приёмка коллектора — фильтр по типам, предмет лизинга в заголовке,
отбор ИНН по ОКВЭД/региону из базы (ТОЛЬКО ЧТЕНИЕ), стоп-типы, кэш guid."""
import io, sys, json, time

sys.path.insert(0, r'C:\sender\_tmp')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import collector_fedresurs as F  # noqa: E402

print('=== A. отбор ИНН из enrich.db по ОКВЭД (чтение, mode=ro) ===')
t0 = time.time()
k1 = F.inn_iz_bazy(okved=['28', '10', '11'], limit=8)
print('  ОКВЭД 28/10/11 -> %d: %s' % (len(k1), [x[0] for x in k1]))
k2 = F.inn_iz_bazy(okved=['28'], regions=['66', '16'], limit=8)
print('  ОКВЭД 28 + регионы 66/16 -> %d: %s' % (len(k2), [x[0] for x in k2]))
k3 = F.inn_iz_bazy(division='meyer', limit=4)
print('  division=meyer -> %d: %s' % (len(k3), [x[0] for x in k3]))
print('  за %.1fс' % (time.time() - t0))

print('\n=== B. справочник типов ===')
m = F.karta_tipov()
print('  названий в справочнике: %d' % len(m))
for nm in ('заключение договора финансовой аренды (лизинга)', 'возникновение права залога',
           'получение лицензии', 'реорганизация юридического лица'):
    print('  %-52s -> %s' % (nm, m.get(nm)))

print('\n=== C. коллектор по явным ИНН, только лизинг ===')
INNS = ['7725104641', '6665002150', '7714572888', '0265004219']
got = F.col_fedresurs(days=365, max_items=12, tipy=['FinancialLeaseContract2'],
                      inns=INNS, pause=0.3, log=lambda s: print('   [лог] ' + s))
print('  item-ов: %d, сводка: %s' % (len(got), F.col_fedresurs.summary))
for it in got[:6]:
    print('   %s | %s | sum=%r | hot=%s' % (it['pubDate'], it['title'][:150], it['sum'],
                                            it.get('hotness')))

print('\n=== D. ФОРМАТ item (ключи строго как у news_scan + наши) ===')
if got:
    need = ['title', 'link', 'pubDate', 'source', 'tier', 'collector', 'query',
            'inn', 'company_name', 'msg_type', 'sum', 'stage']
    have = list(got[0].keys())
    print('  нужные есть: %s' % all(k in have for k in need))
    print('  ключи: %s' % have)
    print(json.dumps(got[0], ensure_ascii=False, indent=1)[:900])

print('\n=== E. стоп-типы (негатив для подавления) ===')
neg = F.col_fedresurs(days=730, max_items=6, tipy=list(F.TIPY_STOP.keys()),
                      inns=['6665002150'], pause=0.3, detali=False)
for it in neg:
    print('   %s | %s | %s' % (it['pubDate'], it['inn'], it['title'][:110]))
print('  стоп-item-ов: %d' % len(neg))

print('\n=== F. кэш ИНН->guid ===')
print('  файл: %s' % F._CACHE_PATH)
t0 = time.time()
F.guid_po_inn('6665002150')
print('  повторный guid_po_inn из кэша за %.3fс' % (time.time() - t0))
print('  записей в кэше: %d' % len(F._cache_load()))
print('\n==== КОНЕЦ ПРОБЫ 14 ====')
