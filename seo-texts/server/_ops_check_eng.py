# -*- coding: utf-8 -*-
"""Гл.инженеры под лупой + откуда взялись «188 человек в 69 компаниях».

Часть А. Для каждого инженера: есть ли фамилия на странице и стоит ли РЯДОМ
с ней записанная должность. Отдельно ищем классическую ошибку парсера —
должность утащили от СОСЕДНЕГО человека: смотрим, чьё имя ближе к слову
«главный инженер» на странице.

Часть Б. Ищем потоковые файлы прогона руководства и считаем, сколько там
людей/компаний на самом деле.
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
ФИО_RE = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{3,}')


def текст(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'),
                 ('&laquo;', '"'), ('&raquo;', '"'), ('&#39;', "'")):
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


def часть_а():
    rows = e.execute(
        "SELECT inn, person, post, role, source_url FROM people WHERE source=? "
        "AND (role LIKE '%инжен%' OR post LIKE '%лавный инженер%')",
        (ИСТ,)).fetchall()
    rows += e.execute(
        "SELECT inn, person, post, role, source_url FROM people WHERE inn IN "
        "('5038107834','6382018657') AND source=?", (ИСТ,)).fetchall()
    вер = 0
    for inn, per, post, role, url in rows:
        html = тянуть(url)
        c = e.execute('SELECT name FROM companies WHERE inn=?',
                      (inn,)).fetchone()
        d = {'инн': inn, 'фио': per, 'должн': post, 'роль': role,
             'компания': (c or [''])[0], 'url': url}
        if not html:
            d['вердикт'] = 'страница НЕ открылась'
            print(json.dumps(d, ensure_ascii=False)[:600])
            continue
        t = текст(html)
        i = t.lower().find(str(per or '').lower())
        if i < 0:
            фам = str(per or '').split()[0]
            i = t.lower().find(фам.lower())
            d['полное_фио_целиком'] = False
        else:
            d['полное_фио_целиком'] = True
        if i < 0:
            d['вердикт'] = 'ФИО НЕ НАЙДЕНО на странице'
            print(json.dumps(d, ensure_ascii=False)[:600])
            continue
        окно = t[max(0, i - 160):i + 160]
        d['должность_рядом'] = bool(re.search(
            r'лавн\w+\s+инженер|ехнич\w+\s+директор', окно, re.I))
        d['окно'] = окно
        # чьё имя ближе всего к слову «главный инженер»
        for m in re.finditer(r'[Гг]лавн\w+\s+инженер\w*', t):
            зона = t[max(0, m.start() - 120):m.end() + 120]
            имена = ФИО_RE.findall(зона)
            d.setdefault('у_слова_гл_инженер', []).append(
                {'кусок': зона[:200], 'имена': имена[:3]})
        вер += 1 if d.get('должность_рядом') else 0
        print(json.dumps(d, ensure_ascii=False)[:1400])
    print('ЧАСТЬ_А записей=%d должность_рядом=%d' % (len(rows), вер))


def часть_б():
    каталоги = [r'C:\seostat\drop', r'C:\seostat', r'C:\sender\server']
    найдено = []
    for k in каталоги:
        try:
            for f in os.listdir(k):
                if re.search(r'(ruk|lead|people|руковод|roles)', f, re.I) and \
                        f.endswith(('.jsonl', '.json', '.log')):
                    p = os.path.join(k, f)
                    найдено.append((p, os.path.getsize(p)))
        except Exception:  # noqa: BLE001
            pass
    print('ПОТОКИ:', json.dumps(найдено, ensure_ascii=False)[:1500])


if __name__ == '__main__':
    часть_а()
    часть_б()
