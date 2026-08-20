#!/usr/bin/env python3
"""Мост между планированием и генератором: final-jobs.jsonl -> формат gen_wave.JOBS.

Конвейер планирования (фазы 1-7) отдаёт джобы в jsonl с полями `url`/`anchor`, а
`gen_wave.py` ждёт список словарей с `links=[(URL, инструкция по якорю)]`. Здесь
перекладка, а заодно последняя проверка перед генерацией: слеш в конце URL, живой
якорь, отсутствие служебных формулировок в угле.

Пишет `wave-jobs.py` — модуль с готовым JOBS, который `gen_wave` импортирует
вместо своего списка (`JOBS_MODULE=wave-jobs`).

    python3 jobs_export.py [--check]     # --check: только проверить, не писать
"""
from __future__ import annotations

import json, os, re, sys

SERVICE_MARKERS = ('промышленная часть появляется', 'часть появляется в разделе',
                   'угол статьи', 'ссылка стоит справкой')


def anchor_hint(j, url, anchor):
    """Инструкция по якорю для промпта генератора.

    Тип якоря выводим из самого текста, а не тащим отдельным полем: брендовые и
    безанкорные ведут себя иначе - их нельзя склонять и нельзя разбавлять.
    """
    naked = bool(re.fullmatch(r'[a-z0-9.-]+\.(ru|com|by|kz|net|info|online)', anchor.strip()))
    brandish = anchor.strip() in ('BERG', 'ENGER', 'ABAC', 'Atlas Copco', 'Компрессор Центр')
    if naked:
        kind = ('безанкорный: поставь ровно домен как есть, без склонения и без '
                'добавления слов вокруг внутри тега')
    elif brandish:
        kind = 'брендовый: имя бренда внутри тега, без товарных слов внутри якоря'
    else:
        kind = ('товарный: текст якоря согласуй по падежу с фразой, в которую он '
                'встаёт; внутри тега только этот текст, без «купить» и «цена», '
                'если их нет в самом якоре')
    return f'{kind}. Текст якоря: «{anchor}»'


def check(j):
    errs = []
    for key in ('slug', 'donor', 'url', 'anchor', 'angle', 'skeleton', 'donor_note'):
        if not (j.get(key) or '').strip():
            errs.append(f'пустое поле {key}')
    for u in (j.get('url'), j.get('url2')):
        if u and not u.rstrip().endswith('/'):
            errs.append(f'URL без слеша в конце: {u}')
        if u and '//' in u.replace('https://', ''):
            errs.append(f'двойной слеш в пути: {u}')
    low = (j.get('angle') or '').lower()
    for m in SERVICE_MARKERS:
        if m in low:
            errs.append(f'служебная формулировка в угле: «{m}»')
    # Агенты пишут скелет либо стрелками, либо нумерованным списком - оба формата
    # валидны, считаем разделы по любому из них.
    sk = j.get('skeleton') or ''
    n_sec = max(len(re.split(r'->|→', sk)), len(re.findall(r'^\s*\d+\.', sk, re.M)))
    if n_sec < 3:
        errs.append('скелет короче трёх разделов')
    return errs


def main():
    jobs = [json.loads(l) for l in open('final-jobs.jsonl', encoding='utf-8')
            if l.strip() and not json.loads(l).get('error')]
    cards = {r['domain']: r for r in json.load(open('ml-cards.json', encoding='utf-8'))}
    bad = 0
    out = []
    for j in jobs:
        errs = check(j)
        if errs:
            bad += 1
            print('  %-28s %s' % (j['donor'], '; '.join(errs)[:110]))
        links = [(j['url'], anchor_hint(j, j['url'], j['anchor']))]
        if j.get('url2') and j.get('anchor2'):
            links.append((j['url2'], anchor_hint(j, j['url2'], j['anchor2'])))
        # Квота авторитетных ссылок: худшая трактовка лимита карточки - он считает
        # ВСЕ ссылки статьи, а не только рекламные (как биржа считает на деле,
        # достоверно неизвестно; завернутое размещение дороже недоставленной ссылки
        # на Википедию). Наши ссылки приоритетны и в квоту входят первыми.
        card_lim = int(str(cards.get(j['donor'], {}).get('max_links', '1')).strip() or 1)
        # Потолок 1, а не 2 (решение 19.08): вес статьи делится между всеми
        # исходящими dofollow-ссылками. Одна наша + одна авторитетная = наши 50%;
        # + вторая авторитетная = 33%, треть оплаченного веса за приправу.
        # Редакционность даёт уже один источник, вторая добавляет мало.
        auth_allow = max(0, min(1, card_lim - len(links)))
        out.append(dict(slug=j['slug'], donor=j['donor'], links=links, auth_allow=auth_allow,
                        angle=(j.get('title', '') + '. ' + (j.get('angle') or '')).strip(),
                        case=j.get('case') or 'кейс не нужен',
                        skeleton=j.get('skeleton') or '',
                        donor_note=j.get('donor_note') or '',
                        seo=j.get('seo') or '',
                        mode=j.get('mode') or 'тематический'))
    print('джоб: %d | с замечаниями: %d' % (len(out), bad))
    if '--check' in sys.argv:
        return 1 if bad else 0
    body = ['# Сгенерировано jobs_export.py из final-jobs.jsonl — правки вносить ТАМ.',
            '# Источник решений: OWNER-DECISIONS.md, раскладка: dispatch.json.', '',
            'JOBS = [']
    for j in out:
        body.append(' dict(')
        for k, v in j.items():
            body.append(f'  {k}={v!r},')
        body.append(' ),')
    body.append(']')
    open('wave-jobs.py', 'w', encoding='utf-8').write('\n'.join(body) + '\n')
    print('записано: wave-jobs.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
