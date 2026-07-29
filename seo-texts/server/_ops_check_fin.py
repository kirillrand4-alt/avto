# -*- coding: utf-8 -*-
"""Добивка: три открытых вопроса.

A) 6318101450 — телефон гл.технолога, которого нет ни на одной странице кэша.
Б) 3525392360 Перхин + «доб. 0100» — его ли добавочный.
В) Откуда взялись 188 человек в 69 компаниях: объединяем все lead-потоки.
"""
import gzip
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx
КЭШ = r'C:\seostat\drop\pagecache'


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h or '')
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


def кэш(inn):
    p = os.path.join(КЭШ, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return None
    return json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))


def А():
    inn = '6318101450'
    d = кэш(inn)
    if not d:
        print('  кэша нет')
        return
    pages = d.get('pages') or []
    print('  страниц в кэше=%d' % len(pages))
    for p in pages[:12]:
        print('    ', str(p.get('url'))[:100])
    rows = e.execute("SELECT phone, person, role, source_url FROM "
                     "phone_contacts WHERE inn=? AND source='сайт компании'",
                     (inn,)).fetchall()
    print('  телефонов в БД=%d' % len(rows))
    for ph, per, rl, url in rows[:10]:
        print('    %s | %s | %s | %s' % (ph, per, rl, str(url)[:70]))
    # ищем «228-23-47» в СЫРОМ html (вдруг спрятан в тегах/атрибутах)
    for p in pages:
        h = p.get('html') or ''
        if '228-23-47' in h or '2282347' in h:
            i = h.find('228-23-47')
            if i < 0:
                i = h.find('2282347')
            print('  НАЙДЕН В СЫРОМ HTML на %s: %s'
                  % (str(p.get('url'))[:60], h[max(0, i - 150):i + 100]))
            break
    else:
        print('  В СЫРОМ HTML КЭША НОМЕРА НЕТ ВООБЩЕ')


def Б():
    inn = '3525392360'
    d = кэш(inn)
    if not d:
        print('  кэша нет')
        return
    for p in (d.get('pages') or []):
        t = текст(p.get('html'))
        for m in re.finditer(r'Перхин', t):
            print('  %s :: %s' % (str(p.get('url'))[:60],
                                  t[max(0, m.start() - 200):m.start() + 200]))
        if '0100' in t:
            i = t.find('0100')
            print('  0100 :: %s' % t[max(0, i - 200):i + 120])


def В():
    инны, всего = set(), 0
    поимённо = {}
    for f in os.listdir(r'C:\seostat\drop'):
        if not re.match(r'(lead|leadership)', f) or not f.endswith('.jsonl'):
            continue
        p = os.path.join(r'C:\seostat\drop', f)
        s, c = 0, 0
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            k = x.get('людей')
            n = k if isinstance(k, int) else (len(k) if isinstance(k, list)
                                              else 0)
            if n:
                s += n
                c += 1
                инны.add(str(x.get('inn')))
        поимённо[f] = (s, c)
        всего += s
    print('  по файлам:', json.dumps(поимённо, ensure_ascii=False))
    print('  СУММА людей по всем lead-потокам=%d уник компаний с людьми=%d'
          % (всего, len(инны)))
    # сколько из этих компаний реально дожили до people
    живых = 0
    for i in инны:
        if e.execute("SELECT 1 FROM people WHERE inn=? AND source='сайт:"
                     "руководство' LIMIT 1", (i,)).fetchone():
            живых += 1
    print('  из них есть в people(сайт:руководство)=%d' % живых)


if __name__ == '__main__':
    print('=== А 6318101450 ===')
    А()
    print('=== Б Перхин ===')
    Б()
    print('=== В потоки руководства ===')
    В()
