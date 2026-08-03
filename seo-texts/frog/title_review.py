# -*- coding: utf-8 -*-
"""Неоптимальные тайтлы/дескрипшены по данным последнего месяца.
1) Механический отбор: pos<=12, показы>=150, CTR < 35% нормы позиции (B2B-кривая),
   без berg-compressor.com (клик-боты). Ранжир по показам, топ-80.
2) Выгрузка живых title/description/h1 каждой страницы.
3) Дебаты двух экспертов 5 кругов на пачку по 8 страниц:
   A - «оптимизатор» (тайтл виноват, предлагает новый),
   B - «скептик» (боты/позиция/интент, тайтл не трогать) - опровергают друг друга.
   Финальный вердикт судьи по каждой странице.
Выход: frog/title-review.json + frog/title-review.xlsx"""
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
sys.path.insert(0, DIR)
import gen_provider as gp
from acceptor_value import ctr  # B2B-кривая

CACHE = os.path.join(DIR, 'title-cache')
os.makedirs(CACHE, exist_ok=True)


def select_pages():
    rows = []
    for line in open(os.path.join(DIR, 'stats-urls.tsv')):
        if line.startswith('url\t'):
            continue
        url, site, pos, shows, clicks = line.rstrip('\n').split('\t')
        pos, shows, clicks = float(pos), int(shows), int(clicks)
        if site == 'berg-compressor.com' or pos > 12 or shows < 150:
            continue
        norm = ctr(pos)
        if clicks / shows < 0.35 * norm:
            rows.append(dict(url=url, site=site, pos=pos, shows=shows, clicks=clicks,
                             ctr=round(clicks / shows * 100, 2),
                             norm_ctr=round(norm * 100, 2)))
    rows.sort(key=lambda r: -r['shows'])
    return rows[:80]


def fetch_meta(r):
    try:
        h = subprocess.run(['curl', '-sL', '-m', '20', r['url']],
                           capture_output=True, timeout=30).stdout.decode('utf-8', 'replace')
        t = re.search(r'<title[^>]*>(.*?)</title>', h, re.S)
        d = re.search(r'name="description"[^>]*content="([^"]*)"', h) or \
            re.search(r'content="([^"]*)"[^>]*name="description"', h)
        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        r['title'] = re.sub(r'\s+', ' ', t.group(1)).strip()[:250] if t else ''
        r['description'] = (d.group(1).strip()[:400] if d else '')
        r['h1'] = re.sub(r'<[^>]+>', '', h1.group(1)).strip()[:200] if h1 else ''
    except Exception as e:
        r['title'] = r['description'] = r['h1'] = f'[fetch fail {e!r}]'[:60]
    return r


def debate(batch, client, bi):
    cf = os.path.join(CACHE, f'batch{bi}.json')
    if os.path.exists(cf):
        return json.load(open(cf))
    data = json.dumps(batch, ensure_ascii=False)
    ROLE_A = ('Ты эксперт-оптимизатор сниппетов (B2B промоборудование). Позиция: у этих страниц '
              'CTR сильно ниже нормы позиции - тайтл/дескрипшен не продают. Для каждой страницы: '
              'диагноз, что не так, и КОНКРЕТНЫЙ новый title (<=65 симв) + description (150-160).')
    ROLE_B = ('Ты скептик-аналитик поисковых данных. Позиция: низкий CTR чаще объясняется '
              'бот-показами (нишу сканируют), запросным миксом (средняя позиция врёт), '
              'интент-мисматчем или отсутствием цены в сниппете - а не текстом тайтла. '
              'Опровергай оппонента постранично, где он неправ.')
    msgs = [{'role': 'user', 'content':
             f'{ROLE_A}\n\nДанные страниц (позиция, показы, клики, CTR, норма CTR, живые title/description/h1):\n{data}\n\nТвой раунд 1: диагноз и предложения по каждой странице.'}]
    transcript = []
    for rnd in range(5):
        role = ROLE_B if rnd % 2 == 0 else ROLE_A
        msg = gp.call(client, msgs, model='claude-fable-5', effort='medium')
        txt = ''.join(b.text for b in msg.content if b.type == 'text')
        transcript.append(txt)
        msgs += [{'role': 'assistant', 'content': txt},
                 {'role': 'user', 'content':
                  f'{role}\n\nРаунд {rnd+2}: опровергни конкретные пункты оппонента выше (постранично), '
                  'признай, где он прав. Кратко, по делу.'}]
    msgs += [{'role': 'assistant', 'content': transcript[-1]},
             {'role': 'user', 'content':
              'Ты судья дебатов. По КАЖДОЙ странице вынеси финальный вердикт с учётом всех раундов. '
              'Верни ТОЛЬКО JSON {"pages": [{"url": "...", "verdict": "тайтл_виноват|боты|позиция_микс|'
              'интент|цена_в_сниппете|смешанно", "confidence": 0.0-1.0, "why": "кратко", '
              '"new_title": "... или null", "new_description": "... или null"}]}'}]
    msg = gp.call(client, msgs, model='claude-fable-5', effort='high')
    verdict = gp.parse_json(msg)
    out = dict(verdict=verdict, rounds=len(transcript) + 1)
    json.dump(out, open(cf, 'w'), ensure_ascii=False)
    return out


def main():
    pages = select_pages()
    print(f'кандидатов с провальным CTR: {len(pages)}', flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        pages = list(ex.map(fetch_meta, pages))
    client = gp.make_client()
    allv = []
    for bi in range(0, len(pages), 8):
        batch = pages[bi:bi + 8]
        try:
            res = debate(batch, client, bi // 8)
            vs = res['verdict'].get('pages', [])
            allv += vs
            print(f'  пачка {bi//8+1}: вердиктов {len(vs)}', flush=True)
        except Exception as e:
            print(f'  пачка {bi//8+1} сбой: {e!r}'[:120], flush=True)
    bym = {v['url'].rstrip('/'): v for v in allv if v.get('url')}
    for p in pages:
        p.update(bym.get(p['url'].rstrip('/'), {}))
    json.dump(pages, open(os.path.join(DIR, 'title-review.json'), 'w'),
              ensure_ascii=False, indent=1)

    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Тайтлы-ревью'
    ws.append(['URL', 'Сайт', 'Поз', 'Показы', 'Клики', 'CTR %', 'Норма %', 'Вердикт',
               'Увер.', 'Почему', 'Текущий title', 'Новый title', 'Новый description'])
    for c in ws[1]: c.font = Font(bold=True)
    for p in pages:
        ws.append([p['url'], p['site'], p['pos'], p['shows'], p['clicks'], p['ctr'],
                   p['norm_ctr'], p.get('verdict', '?'), p.get('confidence', ''),
                   (p.get('why') or '')[:200], p.get('title', ''),
                   p.get('new_title') or '', p.get('new_description') or ''])
    for col, w in zip('ABCDEFGHIJKLM', (66, 20, 6, 8, 7, 7, 8, 15, 6, 40, 45, 45, 50)):
        ws.column_dimensions[col].width = w
    wb.save(os.path.join(DIR, 'title-review.xlsx'))
    from collections import Counter
    print('вердикты:', dict(Counter(p.get('verdict', '?') for p in pages)), flush=True)
    print('=== ТАЙТЛ-РЕВЬЮ ГОТОВО ===', flush=True)


if __name__ == '__main__':
    main()
