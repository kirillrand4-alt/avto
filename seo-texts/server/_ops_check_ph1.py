# -*- coding: utf-8 -*-
"""А) откуда 188/69 в потоке. Б) объёмы утверждения №2 по phone_contacts.

Утверждение №2: «переразметка кэша дала +311 телефонов, 292 из них с ролью,
+90 почт». Ищем эту партию по source='сайт компании' и свежему updated_at.
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx


def поток():
    for f in ('leadership_stream.jsonl', 'lead5.jsonl', 'lead_serp.jsonl'):
        p = os.path.join(r'C:\seostat\drop', f)
        if not os.path.exists(p):
            continue
        всего, с_людьми, инны = 0, 0, set()
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            k = x.get('людей')
            n = k if isinstance(k, int) else (len(k) if isinstance(k, list)
                                              else 0)
            всего += n
            if n:
                с_людьми += 1
                инны.add(str(x.get('inn')))
        print('  %-24s сумма_людей=%-5d компаний_с_людьми=%-4d уник_инн=%d'
              % (f, всего, с_людьми, len(инны)))


def телефоны():
    print('--- phone_contacts по source ---')
    for r in e.execute(
            'SELECT source, COUNT(*), COUNT(DISTINCT inn), MIN(updated_at), '
            'MAX(updated_at) FROM phone_contacts GROUP BY source '
            'ORDER BY 2 DESC').fetchall():
        print('  %-18s n=%-5s инн=%-4s %s .. %s' % r)
    print('--- «сайт компании» по дням ---')
    for r in e.execute(
            "SELECT substr(updated_at,1,10) d, COUNT(*), COUNT(DISTINCT inn) "
            "FROM phone_contacts WHERE source='сайт компании' GROUP BY d "
            "ORDER BY d").fetchall():
        print('  %s n=%-5s инн=%s' % r)
    print('--- роли в «сайт компании» ---')
    for r in e.execute(
            "SELECT COALESCE(NULLIF(role,''),'(пусто)'), COUNT(*) FROM "
            "phone_contacts WHERE source='сайт компании' GROUP BY 1 "
            "ORDER BY 2 DESC").fetchall():
        print('  %-24s %s' % r)
    n, безроли, сфио = e.execute(
        "SELECT COUNT(*), SUM(CASE WHEN COALESCE(role,'')='' THEN 1 ELSE 0 "
        "END), SUM(CASE WHEN COALESCE(person,'')<>'' THEN 1 ELSE 0 END) "
        "FROM phone_contacts WHERE source='сайт компании'").fetchone()
    print('ИТОГ2 сайт_компании=%d без_роли=%s с_фио=%s' % (n, безроли, сфио))


if __name__ == '__main__':
    print('=== ПОТОК РУКОВОДСТВА ===')
    поток()
    print('=== ТЕЛЕФОНЫ ===')
    телефоны()
