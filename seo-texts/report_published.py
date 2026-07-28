# -*- coding: utf-8 -*-
"""Сводка по check-published.jsonl: что встало, что улетело в редирект, где нет текста.

Дополнительно сопоставляет цели редиректов с манифестом: если несколько исходных
URL схлопнулись в одну живую страницу, показывает группу — на такой странице
физически может лежать только один текст.

Выход: check-published-report.md + печать краткой сводки.
"""
import collections, csv, json, os

DIR = os.path.dirname(os.path.abspath(__file__))
JL = os.path.join(DIR, 'check-published.jsonl')
MANIFEST = os.path.join(DIR, 'publish', 'manifest.csv')
MD = os.path.join(DIR, 'check-published-report.md')

ORDER = ['OK', 'REDIRECT_TEXT_OK', 'TEXT_PARTIAL', 'REDIRECT_TEXT_PARTIAL',
         'TEXT_MISSING', 'REDIRECT_TEXT_MISSING', 'HTTP_ERROR', 'FETCH_FAIL', 'CRASH']
TITLES = {
    'OK': 'Текст на месте, редиректа нет',
    'REDIRECT_TEXT_OK': 'Редирект есть, но текст доехал до конечной страницы',
    'TEXT_PARTIAL': 'Без редиректа, текст найден частично',
    'REDIRECT_TEXT_PARTIAL': 'Редирект, текст найден частично',
    'TEXT_MISSING': 'Страница живая (200), текста нет',
    'REDIRECT_TEXT_MISSING': 'Редирект, текста на конечной странице нет',
    'HTTP_ERROR': 'Не 200 (404/5xx)',
    'FETCH_FAIL': 'Не удалось скачать',
    'CRASH': 'Ошибка проверки',
}


def norm_url(u):
    return (u or '').split('?')[0].rstrip('/')


def main():
    recs = []
    with open(JL, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    # дедуп по slug: последняя запись побеждает
    by_slug = {r['slug']: r for r in recs}
    recs = list(by_slug.values())

    with open(MANIFEST, encoding='utf-8-sig') as f:
        man = {r['slug']: r for r in csv.DictReader(f, delimiter=';')}
    manifest_urls = {norm_url(r['url']): s for s, r in man.items()}

    buckets = collections.defaultdict(list)
    for r in recs:
        buckets[r.get('status', 'CRASH')].append(r)

    # группы схлопывания: несколько исходных URL -> одна конечная страница
    dests = collections.defaultdict(list)
    for r in recs:
        if r.get('redirected'):
            dests[norm_url(r.get('final_url'))].append(r)
    collisions = {d: rs for d, rs in dests.items() if len(rs) > 1}

    lines = ['# Проверка публикации 759 текстов на prokompressor.ru', '',
             f'Проверено страниц: **{len(recs)}** из {len(man)}.', '',
             '## Сводка', '', '| Статус | Что это значит | Страниц |',
             '|---|---|---|']
    for st in ORDER:
        if buckets.get(st):
            lines.append(f'| `{st}` | {TITLES[st]} | {len(buckets[st])} |')
    lines += ['']

    redirected = [r for r in recs if r.get('redirected')]
    lines += [f'Всего страниц с редиректом: **{len(redirected)}**, '
              f'из них текст доехал до конечного URL: '
              f'**{sum(1 for r in redirected if r.get("status") == "REDIRECT_TEXT_OK")}**.', '']

    for st in ORDER:
        rs = buckets.get(st)
        if not rs or st == 'OK':
            continue
        lines += [f'## {st} — {TITLES[st]} ({len(rs)})', '']
        for r in sorted(rs, key=lambda x: x['slug']):
            lines.append(f"### {r['slug']}")
            lines.append(f"- исходный URL: {r['url']}")
            if r.get('final_url') and norm_url(r['final_url']) != norm_url(r['url']):
                dst = norm_url(r['final_url'])
                tag = f" (есть в манифесте как `{manifest_urls[dst]}`)" if dst in manifest_urls else ' (нет в манифесте)'
                lines.append(f"- редирект → {r['final_url']}{tag}")
                for h in r.get('chain', []):
                    lines.append(f"  - {h['status']} {h['from']} → {h['to']}")
            lines.append(f"- HTTP {r.get('http_status')}, "
                         f"маркеров найдено {r.get('markers_found')}/{r.get('markers_total')}, "
                         f"H2 найден: {r.get('h2_found')}")
            if r.get('canonical'):
                lines.append(f"- canonical: {r['canonical']}")
            if r.get('h1_actual'):
                lines.append(f"- H1 на странице: {r['h1_actual']}")
                lines.append(f"- H1 ожидался: {r.get('h1_expected')}")
            if r.get('error'):
                lines.append(f"- ошибка: {r['error']}")
            lines.append('')

    if collisions:
        lines += [f'## Схлопывания: несколько URL ведут на одну страницу ({len(collisions)})', '',
                  'На одной странице может лежать только один текст — остальные тексты из группы',
                  'опубликованы в никуда либо перезаписали друг друга.', '']
        for dst, rs in sorted(collisions.items(), key=lambda kv: -len(kv[1])):
            own = manifest_urls.get(dst)
            lines.append(f'- **{dst}/** ← {len(rs)} исходных URL'
                         + (f' (сама есть в манифесте как `{own}`)' if own else ''))
            for r in sorted(rs, key=lambda x: x['slug']):
                lines.append(f"  - `{r['slug']}` ({r.get('status')})")
            lines.append('')

    with open(MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    for st in ORDER:
        if buckets.get(st):
            print(f'{st:26} {len(buckets[st]):4}  {TITLES[st]}')
    print(f'\nредиректов всего: {len(redirected)}; схлопываний: {len(collisions)}')
    print(f'отчёт: {MD}')


if __name__ == '__main__':
    main()
