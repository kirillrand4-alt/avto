# -*- coding: utf-8 -*-
"""Сводка по check-published.jsonl + diagnose-published.jsonl.

Разносит проблемные страницы по причинам:
  * DUPLICATE_URL   — исходный URL 301-редиректит на страницу, у которой есть
                      свой корректный текст (потери контента нет, потрачена генерация);
  * REDIRECT_LOST   — 301 на страницу, где нашего текста нет вообще;
  * PARENT_TEXT     — страница живая, но показывает текст родительского раздела;
  * WRONG_SECTION   — на странице лежит текст страницы из другого раздела;
  * PARTIAL         — текст найден частично (правки/обрезка).

Выход: check-published-report.md + check-published-todo.csv
"""
import collections, csv, json, os

DIR = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(DIR, 'check-published.jsonl')
DIAG = os.path.join(DIR, 'diagnose-published.jsonl')
MANIFEST = os.path.join(DIR, 'publish', 'manifest.csv')
MD = os.path.join(DIR, 'check-published-report.md')
TODO = os.path.join(DIR, 'check-published-todo.csv')


def load(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                out[r['slug']] = r
    return out


def nurl(u):
    return (u or '').split('?')[0].rstrip('/')


def parent(u):
    return '/'.join(nurl(u).split('/')[:-1])


def main():
    check, diag = load(CHECK), load(DIAG)
    with open(MANIFEST, encoding='utf-8-sig') as f:
        man = list(csv.DictReader(f, delimiter=';'))
    slug_by_url = {nurl(r['url']): r['slug'] for r in man}

    reasons = {}
    for slug, r in check.items():
        st = r.get('status')
        if st == 'OK':
            continue
        d = diag.get(slug, {})
        dest = nurl(r.get('final_url'))
        dest_slug = slug_by_url.get(dest)
        if r.get('redirected'):
            # цель редиректа сама в манифесте и её собственный текст на месте?
            if dest_slug and check.get(dest_slug, {}).get('status') == 'OK':
                reasons[slug] = ('DUPLICATE_URL', dest_slug)
            else:
                reasons[slug] = ('REDIRECT_LOST', dest_slug)
        elif d.get('verdict') == 'FOREIGN_TEXT':
            owner = d.get('foreign_slug')
            if slug_by_url.get(parent(r['url'])) == owner:
                reasons[slug] = ('PARENT_TEXT', owner)
            else:
                reasons[slug] = ('WRONG_SECTION', owner)
        elif st == 'TEXT_PARTIAL':
            reasons[slug] = ('PARTIAL', None)
        else:
            reasons[slug] = ('NO_TEXT', d.get('verdict'))

    groups = collections.defaultdict(list)
    for slug, (why, extra) in reasons.items():
        groups[why].append((slug, extra))

    ok = sum(1 for r in check.values() if r.get('status') == 'OK')
    L = ['# Проверка публикации 759 текстов на prokompressor.ru', '',
         f'Проверено URL: **{len(check)}** из {len(man)} (все из `publish/manifest.csv`).',
         'Метод: обход каждого URL с отслеживанием 301/302, затем поиск на конечной',
         'странице трёх предложений-маркеров из `publish/plain/<slug>.html`. Для страниц,',
         'где свой текст не найден, второй проход сопоставляет H2 страницы с индексом',
         'всех 759 текстов (плюс бэкап `gen-orig/`) и определяет, чей текст там лежит.', '',
         '## Итог', '', '| Результат | Страниц |', '|---|---|',
         f'| Свой текст на месте | **{ok}** |']
    NAMES = {
        'PARENT_TEXT': 'Показывается текст родительского раздела, своего текста нет',
        'DUPLICATE_URL': '301 на страницу-дубль, у которой свой текст на месте (контент не потерян)',
        'REDIRECT_LOST': '301 на страницу, где нашего текста нет (текст потерян)',
        'WRONG_SECTION': 'Лежит текст страницы из другого раздела',
        'PARTIAL': 'Свой текст найден частично',
        'NO_TEXT': 'Текста нет, владельца определить не удалось',
    }
    for why in ('PARENT_TEXT', 'DUPLICATE_URL', 'REDIRECT_LOST', 'WRONG_SECTION',
                'PARTIAL', 'NO_TEXT'):
        if groups.get(why):
            L.append(f'| {NAMES[why]} | **{len(groups[why])}** |')
    L += ['', f'Итого требуют вмешательства: **{len(reasons) - len(groups.get("DUPLICATE_URL", []))}** '
              f'страниц (дубли-редиректы не считаем — там контент на месте).', '']

    # 1. текст родителя — группируем по родителю
    if groups.get('PARENT_TEXT'):
        byp = collections.defaultdict(list)
        for slug, owner in groups['PARENT_TEXT']:
            byp[owner].append(slug)
        L += [f'## 1. Текст родительского раздела вместо своего — {len(groups["PARENT_TEXT"])} страниц', '',
              'Страница отвечает 200, canonical свой, H1 совпадает с ожидаемым — но текстовый',
              'блок принадлежит родительскому разделу. Визуально текст на странице есть,',
              'поэтому глазами проблема не видна. Свой текст на такие страницы не встал.', '',
              f'Затронуто родительских разделов: {len(byp)}.', '']
        for owner, slugs in sorted(byp.items(), key=lambda kv: -len(kv[1])):
            L.append(f'<details><summary><b>{owner}</b> — его текст показывается на {len(slugs)} дочерних страницах</summary>')
            L.append('')
            for s in sorted(slugs):
                L.append(f'- `{s}` — {check[s]["url"]}')
            L += ['', '</details>', '']

    # 2. дубли
    if groups.get('DUPLICATE_URL'):
        L += [f'## 2. URL-дубли: 301 на страницу со своим текстом — {len(groups["DUPLICATE_URL"])} шт.', '',
              'Для этих URL текст был сгенерирован зря: URL 301-редиректит на другую страницу,',
              'которая есть в манифесте и на которой её собственный текст стоит корректно.',
              'Контент не потерян, действий не требуется — только вычесть из плана регенерации.', '',
              '| Исходный URL (301) | Ведёт на | Слаг цели |', '|---|---|---|']
        for slug, dest in sorted(groups['DUPLICATE_URL']):
            L.append(f'| `{slug}` | {check[slug]["final_url"]} | `{dest}` |')
        L.append('')

    # 3. потерянные редиректы
    if groups.get('REDIRECT_LOST'):
        L += [f'## 3. Редирект с потерей текста — {len(groups["REDIRECT_LOST"])} шт.', '',
              'Исходный URL схлопнут 301-м на страницу, где нашего текста нет вообще.',
              'Текст, написанный под этот URL, нигде не опубликован.', '']
        for slug, dest in sorted(groups['REDIRECT_LOST']):
            r = check[slug]
            L += [f'### `{slug}`', f'- было: {r["url"]}', f'- стало: {r["final_url"]}'
                  + (f' (в манифесте как `{dest}`)' if dest else ' (в манифесте отсутствует)'),
                  f'- H1 на конечной странице: {r.get("h1_actual")}',
                  f'- H1 ожидался: {r.get("h1_expected")}', '']

    # 4. чужой раздел
    if groups.get('WRONG_SECTION'):
        L += [f'## 4. Текст из другого раздела — {len(groups["WRONG_SECTION"])} шт.', '',
              'Самое грубое: на странице стоит текст, тематически к ней не относящийся.',
              'Здесь и пользователь, и поиск видят нерелевантный контент.', '']
        for slug, owner in sorted(groups['WRONG_SECTION']):
            d = diag.get(slug, {})
            L += [f'### `{slug}`', f'- URL: {check[slug]["url"]}',
                  f'- лежит текст страницы: `{owner}`',
                  f'- H2 на странице: {"; ".join(d.get("page_h2", [])[:4])}', '']

    for why in ('PARTIAL', 'NO_TEXT'):
        if groups.get(why):
            L += [f'## {NAMES[why]} — {len(groups[why])} шт.', '']
            for slug, extra in sorted(groups[why]):
                L.append(f'- `{slug}` — {check[slug]["url"]}'
                         + (f' (маркеров {check[slug].get("markers_found")}'
                            f'/{check[slug].get("markers_total")})' if why == 'PARTIAL' else ''))
            L.append('')

    with open(MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    # машиночитаемый список к переливке (дубли-редиректы исключены — там всё на месте)
    with open(TODO, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['slug', 'url', 'причина', 'что_лежит_сейчас',
                    'файл_без_разметки', 'файл_с_разметкой'])
        for slug, (why, extra) in sorted(reasons.items()):
            if why == 'DUPLICATE_URL':
                continue
            w.writerow([slug, check[slug]['url'], why, extra or '',
                        f'plain/{slug}.html', f'schema/{slug}.html'])

    print(f'свой текст на месте: {ok}')
    for why in ('PARENT_TEXT', 'DUPLICATE_URL', 'REDIRECT_LOST', 'WRONG_SECTION',
                'PARTIAL', 'NO_TEXT'):
        if groups.get(why):
            print(f'{why:16} {len(groups[why]):4}  {NAMES[why]}')
    print(f'\nотчёт: {MD}')


if __name__ == '__main__':
    main()
