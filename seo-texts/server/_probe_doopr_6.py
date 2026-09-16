# -*- coding: utf-8 -*-
"""Проба 6: подбор порога редкости токена (Korpus.RARE) по честной проверке.

На корпусе 8 тыс записей df растёт, и порог «редкий = df<=3» душит охват. Меряем
охват/точность при RARE=3,5,8,12 на отложенной выборке (имя спрятано) и заодно
смотрим, сколько безымянных спасается при каждом пороге. Выбираем максимальный
охват при точности не ниже ~80%.

Только чтение, без сети и денег. Итог печатается ПОСЛЕДНИМ.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\_tmp')
sys.path.insert(0, r'C:\sender\server')
import doopredelenie as DP  # noqa: E402

JS = r'C:\sender\server\news_stream.jsonl'
DB = r'C:\sender\enrich.db'

recs = []
for line in open(JS, encoding='utf-8', errors='replace'):
    line = line.strip()
    if line:
        try:
            recs.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
named = [r for r in recs if (r.get('company') or '').strip()]
anon = [r for r in recs if not (r.get('company') or '').strip()]
iz_bd = DP.Korpus.iz_bd(DB).zapisi


def norm(s):
    return re.sub(r'[^а-яёa-z0-9]', '', (s or '').lower())[:14]


def sobrat(rare):
    DP.Korpus.RARE = rare
    k = DP.Korpus()
    for r in named:
        k.dobavit(r)
    for z in iz_bd:
        k.dobavit(z)
    return k.gotov()


itogi = []
for rare in (3, 5, 8, 12):
    k = sobrat(rare)
    ctx = DP.Kontekst(korpus=k, internet=False, razresheno_platit=False,
                      dadata=lambda imya: None)
    step = max(1, len(named) // 1000)
    pr = otv = ver = pochti = 0
    for i in range(0, len(named), step):
        r = named[i]
        pr += 1
        res = DP.doopredelit({'title': r.get('title'), 'what': r.get('what'),
                              'region': r.get('region'), 'source_url': r.get('source_url'),
                              'source_name': r.get('source_name'),
                              'published': r.get('published')}, ctx)
        if not res.get('company'):
            continue
        otv += 1
        a, b = norm(r.get('company')), norm(res.get('company'))
        if (r.get('inn') and r.get('inn') == res.get('inn')) or (a and a == b):
            ver += 1
        elif a and b and (a[:6] in b or b[:6] in a):
            pochti += 1        # то же имя в другом написании/аббревиатуре
    spas = 0
    for r in anon:
        res = DP.doopredelit({'title': r.get('title'), 'what': r.get('what'),
                              'region': r.get('region'), 'source_url': r.get('source_url'),
                              'source_name': r.get('source_name'),
                              'published': r.get('published')}, ctx)
        if res.get('company'):
            spas += 1
    itogi.append((rare, pr, otv, ver, pochti, spas))

print()
print('==================== ИТОГ (главное) ====================')
print('корпус: %d записей с именем (jsonl %d + signals %d); безымянных %d'
      % (len(named) + len(iz_bd), len(named), len(iz_bd), len(anon)))
print('RARE | проверено | дал ответ (охват) | точно | почти (др. написание) | спасено безымянных')
for rare, pr, otv, ver, pochti, spas in itogi:
    print('%4d | %9d | %5d (%.1f%%) | %4d (%.0f%%) | %d (%.0f%% суммарно) | %d (%.1f%%)'
          % (rare, pr, otv, 100.0 * otv / max(1, pr), ver, 100.0 * ver / max(1, otv),
             pochti, 100.0 * (ver + pochti) / max(1, otv), spas, 100.0 * spas / max(1, len(anon))))
