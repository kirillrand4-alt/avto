# -*- coding: utf-8 -*-
"""Патенты предприятий из нашего списка: ФИО изобретателей с привязкой к юрлицу.

Зачем. Патент — один из немногих открытых документов, где **ФИО стоит рядом с названием
предприятия** и обе стороны проверяемы. Ограничение известно заранее: изобретатель мог
уволиться, а патент остаться, поэтому ценность падает с возрастом документа.

Почему заново. Прошлый заход упёрся в HTTP 503 Google Patents, и нули по шести компаниям
были объявлены **недостоверными** — по правилу «ноль почти всегда своя ошибка». Здесь взят
другой вход: `patents.google.com/xhr/query`, он отдаёт JSON и из песочницы работает.

Использование:
    python3 patenty_harvest.py <predpriyatiya.csv> <out.csv> [--limit 40] [--pauza 4]

Входной CSV: колонки `inn_zakazchika` и `zakazchik`.
"""
import collections
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def chistoe_imya(s):
    """Из «ПАО "КАЗАНЬОРГСИНТЕЗ"» сделать поисковую строку без формы и кавычек."""
    s = re.sub(r'\((?:ИНН|инн)[^)]*\)', ' ', s)
    s = re.sub(r'[«»"\']', ' ', s)
    s = re.sub(r'\b(ПАО|ОАО|АО|ООО|ЗАО|НАО|ПУБЛИЧНОЕ|АКЦИОНЕРНОЕ|ОБЩЕСТВО|С|ОГРАНИЧЕННОЙ|'
               r'ОТВЕТСТВЕННОСТЬЮ)\b', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()


def zapros(text, pauza, popytok=3):
    url = ('https://patents.google.com/xhr/query?url='
           + urllib.parse.quote('q=' + text) + '&exp=')
    req = urllib.request.Request(url, headers={'User-Agent': UA,
                                               'Accept': 'application/json'})
    for p in range(popytok):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception as e:  # noqa: BLE001
            # 503 — то, на чём прошлый заход остановился и записал ложные нули.
            # Здесь он не повод для вывода, а повод подождать подольше.
            print(f'    попытка {p + 1}: {type(e).__name__} {e}', file=sys.stderr)
            time.sleep(pauza * (p + 2))
    return None


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: patenty_harvest.py <predpriyatiya.csv> <out.csv> '
                 '[--limit N] [--pauza SEC]')
    src, out_path = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 40
    pauza = float(sys.argv[sys.argv.index('--pauza') + 1]) if '--pauza' in sys.argv else 4.0

    cnt = collections.Counter()
    imena = {}
    for r in csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';'):
        i = (r.get('inn_zakazchika') or '').strip()
        if i:
            cnt[i] += 1
            imena[i] = (r.get('zakazchik') or '').strip()
    top = [i for i, _ in cnt.most_common(limit)]
    print(f'предприятий к обходу: {len(top)}, пауза {pauza} с', file=sys.stderr)

    cols = ['inn', 'predpriyatie', 'zapros', 'vsego_naydeno', 'nomer', 'data', 'nazvanie',
            'zayavitel', 'izobretateli']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    vsego = 0
    for k, inn in enumerate(top, 1):
        name = chistoe_imya(imena[inn])
        q = f'{name} компрессор'
        d = zapros(q, pauza)
        if d is None:
            print(f'[{k}/{len(top)}] {name[:34]}: НЕ ОТВЕТИЛ — это не ноль, а сбой',
                  file=sys.stderr)
            time.sleep(pauza)
            continue
        res = (d.get('results') or {})
        total = res.get('total_num_results', 0)
        items = []
        for cl in res.get('cluster', []):
            items.extend(cl.get('result', []))
        n = 0
        for it in items:
            p = it.get('patent', {})
            w.writerow({'inn': inn, 'predpriyatie': imena[inn], 'zapros': q,
                        'vsego_naydeno': total,
                        'nomer': p.get('publication_number', ''),
                        'data': p.get('publication_date', ''),
                        'nazvanie': (p.get('title') or '')[:200],
                        'zayavitel': (p.get('assignee') or '')[:160],
                        'izobretateli': (p.get('inventor') or '')[:200]})
            n += 1
        vsego += n
        f.flush()
        print(f'[{k}/{len(top)}] {name[:34]:<34} счётчик {total:>5}, взято {n:>3}, '
              f'всего {vsego}', file=sys.stderr)
        time.sleep(pauza)
    f.close()
    print(f'итого {vsego} строк → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
