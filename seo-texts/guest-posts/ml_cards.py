#!/usr/bin/env python3
"""Карточки площадок Miralinks: лимиты размещения, которых нет в выгрузке.

Выгрузка биржи (26 колонок) отдаёт метрики - ИКС, DR, трафик, спам, цену. Условия
самого размещения живут только в карточке: сколько ссылок и доменов пускают в одну
статью и берут ли НЕТЕМАТИЧЕСКИЕ ссылки. Последнее решает судьбу блоков B и C списка
закупки: там мы ставим ссылку на компрессоры со страницы про цитаты из фильмов, и
площадка с «нетематические - нет» такую статью снимет на модерации.

ID площадки нигде в выгрузке не лежит явно, но он зашит в имя файла скриншота:
.../screenshots/203832.jpeg -> profileView/203832 (сверено с URL из браузера владельца).

Куки сессии биржи - в скратчпаде, chmod 600, в git не попадают. Ходим только на
чтение карточек: ничего не заказываем и не меняем. Пауза между запросами - чтобы
не выглядеть парсером и не потерять аккаунт с балансом.

    python3 ml_cards.py [файл-со-списком-доменов]
"""
import csv, json, os, re, sys, time

import httpx

CK = os.environ.get('ML_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1'
                    '/scratchpad/ml_cookie.txt')
CSV_IN = os.environ.get('ML_CSV', 'miralinks-donors-full.csv')
OUT = os.environ.get('ML_OUT', 'ml-cards.json')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/144.0.0.0 YaBrowser/26.3.0.0 Safari/537.36')

# Метка в карточке -> ключ результата. Порядок значения не имеет: ищем по метке.
FIELDS = {
    'Размещение нетематических ссылок': 'netematic',
    'Максимальное количество ссылок в статье': 'max_links',
    'Максимальное количество доменов в статье': 'max_domains',
    'Участвует в обратном поиске': 'back_search',
    'Уровень вложенности каталога со статьями': 'depth',
    'PR размещение пресс-релизов': 'pr',
    'Статейность': 'statejnost',
    'Индексация статей': 'index_articles',
    'Страниц в индексе': 'pages_idx',
}


def ids_by_domain():
    """Домен -> ID площадки, вытащенный из адреса скриншота."""
    out = {}
    with open(CSV_IN, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            d = (row.get('Домен') or '').strip().lower()
            m = re.search(r'/(\d+)\.jpe?g', row.get('Скрин') or '')
            if d and m and d not in out:
                out[d] = m.group(1)
    return out


def text_lines(html):
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)
    t = re.sub(r'<[^>]+>', '\n', t)
    t = t.replace('&nbsp;', ' ')
    return [l.strip() for l in t.split('\n') if l.strip()]


def parse(html):
    """Значение поля - первая непустая строка после метки.

    Карточка рисует таблицы «метка / значение» соседними ячейками, поэтому текстовый
    срез сохраняет этот порядок. «Индексация статей» и «Страниц в индексе» встречаются
    дважды (Яндекс и Google) - собираем оба вхождения по порядку.
    """
    lines = text_lines(html)
    res, multi = {}, {}
    for i, l in enumerate(lines):
        for label, key in FIELDS.items():
            if l != label:
                continue
            val = lines[i + 1] if i + 1 < len(lines) else ''
            if key in ('index_articles', 'pages_idx', 'statejnost'):
                multi.setdefault(key, []).append(val)
            elif key not in res:
                res[key] = val
    res['verified'] = 'Вебмастер верифицирован' in lines
    for k, v in multi.items():
        res[k] = ' / '.join(v[:2])
    kw = next((lines[i + 1] for i, l in enumerate(lines) if l == 'Ключевые слова'), '')
    res['keywords'] = kw[:200]
    return res


def main():
    doms = [l.strip().lower() for l in open(sys.argv[1], encoding='utf-8') if l.strip()] \
        if len(sys.argv) > 1 else []
    ids = ids_by_domain()
    done = {}
    if os.path.exists(OUT):
        done = {r['domain']: r for r in json.load(open(OUT, encoding='utf-8')) if not r.get('error')}
    todo = [d for d in doms if d not in done]
    print(f'доменов: {len(doms)} | уже есть: {len(done)} | к запросу: {len(todo)}', flush=True)
    ck = open(CK, encoding='utf-8').read().strip()
    hdr = {'cookie': ck, 'user-agent': UA, 'accept-language': 'ru,en;q=0.9',
           'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           'referer': 'https://www.miralinks.com/catalog?s_catalog_type=yandex'}
    res = list(done.values())
    with httpx.Client(timeout=60, headers=hdr, follow_redirects=True) as c:
        for i, d in enumerate(todo, 1):
            sid = ids.get(d)
            if not sid:
                res.append({'domain': d, 'error': 'нет ID в выгрузке'})
                print(f'  {d:28} нет ID', flush=True)
                continue
            try:
                r = c.get(f'https://www.miralinks.com/catalog/profileView/{sid}')
                rec = {'domain': d, 'id': sid, **parse(r.text)}
            except Exception as e:                           # noqa: BLE001
                rec = {'domain': d, 'id': sid, 'error': repr(e)[:120]}
            res.append(rec)
            json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print('  [%d/%d] %-28s ссылок=%-4s доменов=%-4s нетематические=%-6s %s' % (
                i, len(todo), d, rec.get('max_links', '?'), rec.get('max_domains', '?'),
                rec.get('netematic', '?'), rec.get('error', '')), flush=True)
            time.sleep(2.5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
