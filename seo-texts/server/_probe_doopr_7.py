# -*- coding: utf-8 -*-
"""Проба 7 (та же, сводка в самом конце): боевая проверка МОДУЛЯ doopredelenie.py на реальных данных сервера.

Что делает:
  1) строит корпус из news_stream.jsonl + signals (enrich.db, mode=ro);
  2) честная проверка: у именованных записей ПРЯЧЕТ имя и просит модуль его найти —
     считаем охват и точность (сравнение с настоящими ИНН/именем);
  3) гоняет модуль по всем безымянным событиям (company пусто) — сколько спасается;
  4) считает, что бы легло в кучу и с какими уликами (какой путь чаще всего «не смог»).

Ничего не пишет, в сеть не ходит (internet=False), платные пути выключены,
провайдера не зовёт. Итог печатается ПОСЛЕДНИМ.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\_tmp')      # сюда раннер кладёт залитые скрипты
sys.path.insert(0, r'C:\sender\server')
import doopredelenie as DP                 # noqa: E402

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

korpus = DP.Korpus()
for r in named:
    korpus.dobavit(r)
n_jsonl = len(korpus.zapisi)
kb = DP.Korpus.iz_bd(DB)                   # signals + companies
for z in kb.zapisi:
    korpus.dobavit(z)
korpus.gotov()
print('корпус: %d из jsonl + %d из signals = %d' % (n_jsonl, len(kb.zapisi), len(korpus.zapisi)))

ctx = DP.Kontekst(korpus=korpus, internet=False, razresheno_platit=False,
                  dadata=lambda imya: None)          # ни сети, ни денег, ни dadata


def norm(s):
    return re.sub(r'[^а-яёa-z0-9]', '', (s or '').lower())[:14]


# ---- (2) честная проверка с прятанием имени
step = max(1, len(named) // 1000)
proverено = otvet = verno = 0
oshibki = []
for i in range(0, len(named), step):
    r = named[i]
    proverено += 1
    sob = {'title': r.get('title'), 'what': r.get('what'), 'region': r.get('region'),
           'source_url': r.get('source_url'), 'source_name': r.get('source_name'),
           'published': r.get('published')}
    res = DP.doopredelit(sob, ctx)
    if not res.get('company'):
        continue
    otvet += 1
    ok = (r.get('inn') and r.get('inn') == res.get('inn')) or \
         (norm(r.get('company')) and norm(r.get('company')) == norm(res.get('company')))
    if ok:
        verno += 1
    elif len(oshibki) < 6:
        oshibki.append((r.get('company'), res.get('company'), res['uverennost'],
                        (r.get('title') or '')[:60]))

# ---- (3) реальные безымянные
spaseno, po_putyam, uver = 0, {}, {}
primery, prichiny = [], {}
for r in anon:
    sob = {'title': r.get('title'), 'what': r.get('what'), 'region': r.get('region'),
           'source_url': r.get('source_url'), 'source_name': r.get('source_name'),
           'published': r.get('published'), 'event_type': r.get('event_type')}
    res = DP.doopredelit(sob, ctx)
    if res.get('company'):
        spaseno += 1
        po_putyam[res['путь']] = po_putyam.get(res['путь'], 0) + 1
        uver[res['uverennost']] = uver.get(res['uverennost'], 0) + 1
        if len(primery) < 12:
            primery.append(((r.get('title') or '')[:70], res['company'], res['uverennost'],
                            (res['uliki'] or [''])[1][:60] if len(res['uliki']) > 1 else ''))
    else:
        for u in res['uliki']:
            k = u.split(':')[0]
            prichiny[k] = prichiny.get(k, 0) + 1

print('--- ошибки на проверке (истина -> ответ модуля) ---')
for o in oshibki:
    print('  ИСТИНА=%s ОТВЕТ=%s [%s] | %s' % o)
print('--- спасённые безымянные (глазами) ---')
for p in primery:
    print('  %s -> %s [%s] %s' % p)
print()
print('==================== ИТОГ (главное) ====================')
print('news_stream.jsonl: %d записей, с именем %d, БЕЗ имени %d' % (len(recs), len(named), len(anon)))
print('корпус доопределения: %d записей с именем' % len(korpus.zapisi))
print('--- проверка модуля с ПРЯЧЕННЫМ именем (%d записей) ---' % proverено)
print('модуль дал имя: %d (охват %.1f%%), из них верно %d (точность %.0f%%)'
      % (otvet, 100.0 * otvet / max(1, proverено), verno, 100.0 * verno / max(1, otvet)))
print('--- боевые безымянные события ---')
print('доопределено: %d из %d (%.1f%%), пути: %s, уверенность: %s'
      % (spaseno, len(anon), 100.0 * spaseno / max(1, len(anon)), po_putyam, uver))
print('почему не вышло (топ причин по уликам):',
      dict(sorted(prichiny.items(), key=lambda kv: -kv[1])[:6]))
