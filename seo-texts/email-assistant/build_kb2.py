# -*- coding: utf-8 -*-
"""build_kb v2: ЯДРО (answer-kb.json, компактное — в промпт целиком) + РЕТРИВ-СЛОЙ
(kb-retrieve.json, полный — выборка под конкретного лида через kb_retrieve.py).
Расширение по KB-EXPANSION-PLAN.md: все 1018 проектов (с городами), все 303 цены,
ценовые коридоры по бюджет-баллу ОКВЭД (маппинг владельца)."""
import json, os, collections, re

ST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- РЕТРИВ-СЛОЙ (полные данные) ----------
proj = json.load(open(os.path.join(ST, 'projects-index.json')))
projects = []
for p in proj:
    projects.append(dict(
        title=(p.get('h1') or p.get('title') or '')[:110],
        url=p.get('url'), date=p.get('date', ''),
        sphere=(p.get('sphere') or p.get('category') or 'прочее').strip(),
        brand=p.get('brand', ''), equipment=(p.get('equipment') or '')[:90],
        client=(p.get('client') or '')[:60], city=(p.get('city_guess') or '').strip(),
        narrative=(p.get('narrative') or '')[:280]))

bx = json.load(open(os.path.join(ST, 'frog', 'bitrix-prices.json')))
prices_full = dict(by_cat=bx['by_cat'], by_brand_cat=bx['by_brand_cat'])

# ценовые коридоры по бюджет-баллу (шкала владельца, лист «Шкала приоритета»)
budget_bands = {
    'Промышленные компрессоры': {5: '5–30+ млн ₽', 4: '2–10 млн ₽', 3: '0,8–4 млн ₽', 2: '0,25–1,5 млн ₽'},
    'Фотосепараторы': {5: '12–50+ млн ₽', 4: '5–20 млн ₽', 3: '2–8 млн ₽', 2: '1–4 млн ₽'},
    'Рентген-детекторы': {5: '8–30 млн ₽', 4: '4–15 млн ₽', 3: '2–8 млн ₽', 2: '1–4 млн ₽'},
    'Генераторы азота': {5: '5–25+ млн ₽', 4: '3–12 млн ₽', 3: '1,5–6 млн ₽', 2: '0,7–3 млн ₽'},
    'Генераторы кислорода': {5: '6–40+ млн ₽', 4: '3–15 млн ₽', 3: '1,5–8 млн ₽', 2: '0,8–4 млн ₽'},
    'МКС': {5: '10–50+ млн ₽', 4: '5–25 млн ₽', 3: '3–12 млн ₽', 2: '1,5–6 млн ₽'},
}

# гео-агрегаты: «в вашем городе/РЕГИОНЕ N внедрений» (идея линз + владелец).
# город→регион через справочник НП из базы (10229 записей, data/base_settlements.json).
city2region = {}
try:
    st = json.load(open(os.path.join(ST, 'data', 'base_settlements.json')))
    # при коллизии имён городов берём вариант с бОльшим числом компаний (уже отсортировано by n)
    for s in sorted(st, key=lambda x: x.get('n', 0)):
        city2region[s['city'].lower()] = s['region']
except Exception:  # noqa: BLE001
    pass
for p in projects:
    p['region'] = city2region.get((p['city'] or '').lower(), '')

city_counts = collections.Counter(p['city'] for p in projects if p['city'])
region_counts = collections.Counter(p['region'] for p in projects if p['region'])
sphere_counts = collections.Counter(p['sphere'] for p in projects)

retrieve = dict(projects=projects, prices=prices_full, budget_bands=budget_bands,
                city_counts={c: n for c, n in city_counts.items() if n >= 2},
                region_counts={r: n for r, n in region_counts.items() if n >= 2},
                sphere_counts=dict(sphere_counts))
json.dump(retrieve, open(os.path.join(HERE, 'kb-retrieve.json'), 'w'),
          ensure_ascii=False, indent=0)

# ---------- ЯДРО (как v1, оставляем совместимым) ----------
os.system(f'cd {HERE} && python3 build_kb.py >/dev/null 2>&1')

print(f'kb-retrieve: проектов {len(projects)} (городов с 2+: '
      f'{sum(1 for n in city_counts.values() if n >= 2)}), '
      f'цен by_cat {len(prices_full["by_cat"])} / brand_cat {len(prices_full["by_brand_cat"])}, '
      f'размер {os.path.getsize(os.path.join(HERE, "kb-retrieve.json"))//1000}кб')
