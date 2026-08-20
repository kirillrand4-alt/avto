# -*- coding: utf-8 -*-
r"""Список доменов-справочников для пополнения ploshchadki: только то, что добавлять."""
import json, os, sqlite3, sys
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL
ЛОГ = r'C:\sender\poisk_saytov.jsonl'
BD = r'C:\sender\enrich.db'
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
занятые = {}
for инн, s, cs in c.execute("select inn, coalesce(site,''), coalesce(cand_site,'') "
                            "from companies where coalesce(site,'')<>'' "
                            "or coalesce(cand_site,'')<>''"):
    for u in (s, cs):
        д = PL.домен(u) if u else ''
        if д:
            занятые.setdefault(д, set()).add(str(инн))
c.close()
счёт = {}
with open(ЛОГ, encoding='utf-8', errors='replace') as f:
    for s in f:
        try: d = json.loads(s)
        except Exception: continue
        if not d.get('site'): continue
        инн = str(d.get('inn') or '')
        дом = PL.домен(d['site'])
        if (занятые.get(дом) or set()) - {инн}:
            счёт.setdefault(дом, set()).add(инн)
топ = sorted(((д, len(и)) for д, и in счёт.items() if len(и) >= 4
              and not PL.из_списка(д)), key=lambda x: -x[1])
print(json.dumps({'справочников': len(топ),
                  'компаний_за_ними': sum(n for _д, n in топ),
                  'топ60': [{'д': д, 'n': n} for д, n in топ[:60]]},
                 ensure_ascii=False))
