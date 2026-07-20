# -*- coding: utf-8 -*-
"""Мастер-сегментация для персонализации заходов: отрасль(кейсы) × размер базы
(ОКВЭД/оборудование) × топ-клиенты по выручке × регионы. Свод всех источников."""
import os, json, re
from collections import defaultdict, Counter

D = os.path.dirname(os.path.abspath(__file__))
proj = json.load(open(os.path.join(D,'projects-index.json'), encoding='utf-8'))
idx = {o['client']: o for o in json.load(open(os.path.join(D,'client-revenue-index.json'), encoding='utf-8'))}
seg = json.load(open(os.path.join(D,'segments-base.json'), encoding='utf-8'))

CAT_RU = {
 'proizvodstvo':'Производство (общее)','metalloobrabotka':'Металлообработка',
 'pishchevoe-proizvodstvo':'Пищевое производство','avtoservis':'Автосервис/СТО',
 'stroitelnye-raboty':'Строительные работы','peskostruy':'Пескоструйные работы',
 'mebelnoe-proizvodstvo':'Мебельное производство','derevoobrabotka':'Деревообработка',
 'selskoe-khozyaystvo':'Сельское хозяйство','zhelezobetonnye-izdeliya':'ЖБИ / бетон',
 'meditsina-farmatsevtika':'Медицина и фармацевтика','fotoseparatory':'Фотосепараторы (Meyer)',
 'vyduv-pet':'Выдув ПЭТ-тары','geologiya-dobycha':'Геология и добыча',
 'reklamnoe-proizvodstvo':'Рекламное производство','issledovaniya-nauka':'Исследования/наука',
 'dorozhnye-raboty':'Дорожные работы',
}

by_cat = defaultdict(lambda: {'projects':0, 'clients':{}, 'regions':Counter(), 'cities':Counter()})
for r in proj:
    cat = (r.get('category') or '').strip() or 'прочее'
    b = by_cat[cat]
    b['projects'] += 1
    client = (r.get('client') or '').strip()
    info = idx.get(client)
    if info and info.get('revenue'):
        cur = b['clients'].get(client, 0)
        if info['revenue'] > cur: b['clients'][client] = info['revenue']
    if info and info.get('region'):
        b['regions'][info['region']] += 1
    if (r.get('city') or '').strip():
        b['cities'][(r.get('city') or '').strip()] += 1

master = {}
for cat, b in sorted(by_cat.items(), key=lambda x:-x[1]['projects']):
    top = sorted(b['clients'].items(), key=lambda x:x[1], reverse=True)[:6]
    master[cat] = {
        'name': CAT_RU.get(cat, cat),
        'projects': b['projects'],
        'clients_with_revenue': len(b['clients']),
        'top_clients': [{'name':n,'revenue_bln':round(v/1e9,2)} for n,v in top],
        'top_regions': b['regions'].most_common(6),
        'top_cities': b['cities'].most_common(6),
    }
json.dump(master, open(os.path.join(D,'segment-master.json'),'w'), ensure_ascii=False, indent=1)

print("="*78)
print("МАСТЕР-СЕГМЕНТАЦИЯ ПО ОТРАСЛЯМ (источник заходов) — по числу кейсов")
print("="*78)
for cat, m in master.items():
    tc = ', '.join(f"{c['name'][:22]}({c['revenue_bln']}млрд)" for c in m['top_clients'][:3]) or '—'
    print(f"\n▶ {m['name']}  |  кейсов: {m['projects']}  |  клиентов с выручкой: {m['clients_with_revenue']}")
    print(f"   топ-клиенты: {tc}")
    tr = ', '.join(f"{r}({n})" for r,n in m['top_regions'][:4])
    print(f"   топ-регионы: {tr}")

print("\n"+"="*78)
print("РАЗМЕР БАЗЫ ПО ПОТРЕБНОСТИ В ОБОРУДОВАНИИ (кого можно адресовать)")
print("="*78)
for k,v in seg['equipment_all']:
    print(f"  {v:>7}  {k}")
print(f"\nВсего компаний в базе: {seg['rows']} | с выручкой: {seg['rev_known']}")
print("Тиры по размеру (выручка):")
for k,v in sorted(seg['revenue_tiers']):
    print(f"  {v:>7}  {k}")
