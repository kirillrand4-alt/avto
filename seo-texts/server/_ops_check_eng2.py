# -*- coding: utf-8 -*-
"""Компактный вердикт по каждому «главному инженеру» + разбор потоков.

Печатаем коротко: вывод приходит хвостом, длинные окна съедали начало.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None

e = EDB.EnrichDB().cx
ИСТ = 'сайт:руководство'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def тянуть(url):
    try:
        r = requests.get(url, timeout=25, headers={'User-Agent': UA},
                         verify=False)
        b = r.content
        for cand in (r.encoding or 'utf-8', 'utf-8', 'cp1251'):
            try:
                s = b.decode(cand)
                if 'Ð' not in s[:2000]:
                    return s
            except Exception:  # noqa: BLE001
                continue
        return b.decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return None


def инженеры():
    rows = e.execute(
        "SELECT inn, person, post, role, source_url FROM people WHERE source=? "
        "AND role LIKE '%инжен%' ORDER BY inn", (ИСТ,)).fetchall()
    настоящих = 0
    for inn, per, post, role, url in rows:
        html = тянуть(url)
        nm = (e.execute('SELECT name FROM companies WHERE inn=?',
                        (inn,)).fetchone() or [''])[0]
        if not html:
            print('  %s | %s | %s | СТРАНИЦА НЕ ОТКРЫЛАСЬ' % (inn, per, post))
            continue
        t = текст(html)
        i = t.lower().find(str(per or '').lower())
        окно = t[max(0, i - 130):i + 130] if i >= 0 else ''
        реально = bool(re.search(r'лавн\w+\s+инженер', окно, re.I))
        настоящих += 1 if реально else 0
        print('  ИНН=%s | %s | БД:%r | на_странице_гл.инженер=%s | %s' %
              (inn, per, post, реально, nm[:40]))
        if not реально:
            print('     ОКНО: %s' % окно[:260])
    print('ИНЖЕНЕРЫ всего=%d подтверждено=%d' % (len(rows), настоящих))


def потоки():
    for f in ('leadership_stream.jsonl', 'lead2.jsonl', 'lead5.jsonl',
              'lead_serp.jsonl', 'people_merged.jsonl'):
        p = os.path.join(r'C:\seostat\drop', f)
        if not os.path.exists(p):
            continue
        люди, инны, стр = 0, set(), 0
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            стр += 1
            if x.get('inn'):
                инны.add(str(x['inn']))
            for k in ('people', 'персоны', 'найдено', 'items'):
                v = x.get(k)
                if isinstance(v, list):
                    люди += len(v)
                elif isinstance(v, int):
                    люди += v
        print('  %-26s строк=%-5d инн=%-4d людей_в_поле=%d'
              % (f, стр, len(инны), люди))
        # покажем ключи первой строки
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                print('     ключи:', list(json.loads(ln).keys())[:12])
            except Exception:  # noqa: BLE001
                pass
            break


def удалённые():
    p = r'C:\seostat\drop\people_removed.jsonl'
    if not os.path.exists(p):
        print('people_removed.jsonl НЕТ')
        return
    n = 0
    прич = {}
    прим = []
    for ln in io.open(p, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        n += 1
        r = str(x.get('причина') or x.get('reason') or x.get('why') or '?')
        прич[r] = прич.get(r, 0) + 1
        if len(прим) < 6:
            прим.append(json.dumps(x, ensure_ascii=False)[:220])
    print('УДАЛЕНО людей=%d причины=%s' % (n, json.dumps(
        прич, ensure_ascii=False)[:600]))
    for x in прим:
        print('   ', x)


if __name__ == '__main__':
    print('=== ПОТОКИ ===')
    потоки()
    print('=== УДАЛЁННЫЕ ===')
    удалённые()
    print('=== ИНЖЕНЕРЫ ===')
    инженеры()
