# -*- coding: utf-8 -*-
"""Свод по потоку «УТВЕРЖДАЮ»: сколько компаний, карточек и людей."""
import io
import json
import os
import sys

ИМЯ = next((a for a in sys.argv[1:] if a.endswith('.jsonl')), 'utv_tech.jsonl')
ПУТЬ = r'C:\seostat\drop' + '\\' + ИМЯ

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx


def main():
    строк = с_людьми = людей = 0
    if os.path.exists(ПУТЬ):
        for ln in io.open(ПУТЬ, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            строк += 1
            n = int(x.get('людей') or 0)
            if n:
                с_людьми += 1
                людей += n
    # кто записался в базу из этого прогона
    свежие = [dict(zip(('person', 'post', 'role', 'source_url'), r))
              for r in e.execute(
        "SELECT person, post, role, source_url FROM people "
        "WHERE source='zakupki:утверждаю' ORDER BY updated_at DESC LIMIT 20")]
    роли = {}
    for x in свежие:
        роли[x['role'] or '(пусто)'] = роли.get(x['role'] or '(пусто)', 0) + 1
    print(json.dumps({'строк_потока': строк, 'компаний_с_людьми': с_людьми,
                      'людей_по_потоку': людей, 'роли_последних': роли,
                      'последние': свежие[:12]},
                     ensure_ascii=False, indent=1)[:2500])
    # цифры ПОСЛЕДНЕЙ строкой: раннер режет вывод с головы
    тех = ('гл.инженер', 'гл.энергетик', 'гл.механик', 'гл.технолог',
           'гл.конструктор', 'техдиректор', 'нач.производства', 'нач.цеха')
    всего = e.execute("SELECT COUNT(*) FROM people WHERE "
                      "source='zakupki:утверждаю'").fetchone()[0]
    т = e.execute("SELECT COUNT(*) FROM people WHERE source='zakupki:утверждаю' "
                  "AND role IN (%s)" % ','.join('?' * len(тех)), тех).fetchone()[0]
    print(json.dumps({'строк_потока': строк, 'компаний_с_людьми': с_людьми,
                      'людей_по_потоку': людей,
                      'в_базе_из_утверждаю': всего, 'из_них_технических': т,
                      'роли': роли}, ensure_ascii=False))


if __name__ == '__main__':
    main()
