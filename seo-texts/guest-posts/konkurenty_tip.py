#!/usr/bin/env python3
"""Тип площадки из пересечения доноров конкурентов: главная страница -> провайдер.

    python3 konkurenty_tip.py кандидаты.json -> konkurenty-tip.jsonl (дописывается, резюмируемо)

Ahrefs до конца месяца упёрся в месячный лимит строк (SeRowsMonthlyLimitReached),
поэтому тематику по ключам не снять. Берём title/description/h1 главной и просим модель
определить тип: отраслевое СМИ/портал, региональное СМИ, общее СМИ, каталог/справочник,
доска объявлений, блог, сервис, прочее; и связь с нашими темами (наша/смежная/мимо).
"""
import concurrent.futures as cf
import json
import os
import re
import sys

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as GP  # noqa: E402

OUT = os.path.join(DIR, 'konkurenty-tip.jsonl')
MODEL = os.environ.get('CLS_MODEL', 'claude-opus-5-5')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0 Safari/537.36'


def head(dom):
    for u in (f'https://{dom}/', f'http://{dom}/'):
        try:
            r = httpx.get(u, headers={'user-agent': UA}, timeout=20, follow_redirects=True)
            t = r.text[:200000]
            g = lambda p: re.sub(r'\s+', ' ', (re.search(p, t, re.I | re.S) or [None, ''])[1]).strip()[:200]
            return {'title': g(r'<title[^>]*>(.*?)</title>'),
                    'desc': g(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']'),
                    'h1': re.sub('<[^>]+>', '', g(r'<h1[^>]*>(.*?)</h1>'))}
        except Exception:  # noqa: BLE001
            continue
    return {'title': '', 'desc': '', 'h1': '', 'err': 'не открылась'}


PROMPT = '''Ниже площадки, которые ставят ссылки на нескольких продавцов промышленных
компрессоров, насосов и генераторов. Для каждой по домену и главной странице определи:
tip: одно из "отраслевое СМИ/портал", "региональное СМИ", "общее СМИ", "каталог/справочник",
"доска объявлений/маркетплейс", "блог/форум", "сервис", "прочее";
tema: "наша" (промышленное оборудование, компрессоры, пневматика, насосы, энергетика,
металлообработка, производство), "смежная" (стройка, бизнес, промышленность в целом), "мимо";
pochemu: до 10 слов.
Ответ строго JSON-массивом [{"domain":..,"tip":..,"tema":..,"pochemu":..}], без пояснений.

'''


def main():
    c = json.load(open(sys.argv[1], encoding='utf-8'))
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['domain'] for l in open(OUT, encoding='utf-8') if l.strip()}
    todo = [x for x in c if x['domain'] not in done]
    print(f'к разметке: {len(todo)}', flush=True)
    with cf.ThreadPoolExecutor(12) as ex:
        heads = dict(zip([x['domain'] for x in todo], ex.map(head, [x['domain'] for x in todo])))
    for i in range(0, len(todo), 30):
        ch = todo[i:i + 30]
        lines = [json.dumps({'domain': x['domain'], **heads[x['domain']]}, ensure_ascii=False) for x in ch]
        msg = GP.call(None, [{'role': 'user', 'content': PROMPT + '\n'.join(lines)}],
                      model=MODEL, thinking_on=False, max_tokens=8000)
        txt = ''.join(getattr(b, 'text', '') for b in msg.content)
        arr = json.loads(txt[txt.index('['):txt.rindex(']') + 1])
        by = {a['domain']: a for a in arr}
        with open(OUT, 'a', encoding='utf-8') as f:
            for x in ch:
                a = by.get(x['domain'], {})
                f.write(json.dumps({**x, **heads[x['domain']], 'tip': a.get('tip'), 'tema': a.get('tema'),
                                    'pochemu': a.get('pochemu')}, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        print(f'  размечено {i + len(ch)}/{len(todo)}', flush=True)


if __name__ == '__main__':
    main()
