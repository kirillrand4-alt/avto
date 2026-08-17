# -*- coding: utf-8 -*-
r"""Почему 1637 обойденных компаний не дали НИ ОДНОГО блока.

Замер полноты 17.08: из 11864 обойденных у 1637 карточка пуста полностью. Это 14%
всей работы обхода, и прежде чем чинить, надо знать, что именно там — три разные
беды лечатся по-разному:

    страниц нет по существу   — сайт отдал заглушку, редирект или пару строк;
    паспорта нет              — страницы есть, но разбор до них не дошёл;
    паспорт пуст              — разбор прошёл и честно ничего не нашёл;
    привязка не доказана      — страницы чужие или без реквизитов, и мы сами
                                отказались считать блок закрытым.

Считаем каждую причину и показываем примеры с адресами и объёмом текста, чтобы
вывод можно было проверить глазами, а не поверить на слово.

    python nol_blokov.py [сколько примеров]
"""
import gzip
import json
import os
import re
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import polnota_sayta as PS_        # noqa: E402
import sverka_privyazki as SP      # noqa: E402

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
МАЛО_ЗНАКОВ = 4000                 # столько текста не хватит ни на один факт


def _страницы(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return [], 0
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return [], -1
    урлы, знаков = [], 0
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        чистый = re.sub(r'<[^>]+>', ' ', re.sub(
            r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I))
        знаков += len(re.sub(r'\s+', ' ', чистый).strip())
        урлы.append(pg.get('url') or '')
    return урлы, знаков


def разбор(предел_примеров=8):
    все = [r for r in PS_.строки()
           if os.path.exists(os.path.join(KESH, '%s.json.gz' % r['inn']))]
    итог = {'обойденных': len(все), 'пустых_карточек': 0, 'по_причинам': {}}
    примеры = {}
    for r in все:
        if PS_.блоки(r):
            continue
        итог['пустых_карточек'] += 1
        урлы, знаков = _страницы(str(r['inn']))
        есть_паспорт = bool(r['facts']) and r['format'] >= 2
        улики, _ = SP.улики(str(r['inn']), r['name'], r['site'], r['ogrn']) \
            if r['site'] else ([], '')
        if знаков < 0:
            причина = 'кэш не читается'
        elif знаков < МАЛО_ЗНАКОВ:
            причина = 'страниц по существу нет (текста меньше %d знаков)' % МАЛО_ЗНАКОВ
        elif not есть_паспорт:
            причина = 'текст есть, паспорта нет — разбор не дошёл'
        elif not улики:
            причина = 'текст и паспорт есть, привязка не доказана'
        else:
            причина = 'разбор прошёл и ничего не нашёл'
        итог['по_причинам'][причина] = итог['по_причинам'].get(причина, 0) + 1
        сп = примеры.setdefault(причина, [])
        if len(сп) < предел_примеров:
            сп.append({'инн': str(r['inn']), 'имя': r['name'][:38],
                       'сайт': r['site'], 'страниц': len(урлы), 'знаков': знаков,
                       'адреса': [u[:60] for u in урлы[:3]]})
    итог['примеры'] = примеры
    return итог


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5
    и = разбор(n)
    прим = и.pop('примеры', {})
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
