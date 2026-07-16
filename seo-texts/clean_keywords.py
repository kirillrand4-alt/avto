# -*- coding: utf-8 -*-
"""Чистка вебмастерских фраз через Fable API: оставить только те, что пользователь
мог бы вбить в поиск ПО САЙТУ компрессорного магазина."""
import json, re, sys

import openpyxl

from gen_provider import make_client, call

XLSX = '/root/.claude/uploads/bcce55cd-293a-515c-9700-ae71a77daa5a/d1e83e3f-keywords_all_20260101_20260714.xlsx'

PROMPT = """Ты готовишь тестовый набор для проверки внутреннего поиска интернет-магазина
промышленных компрессоров prokompressor.ru (винтовые/поршневые компрессоры, осушители,
ресиверы, запчасти). Ниже - фразы, по которым сайт ПОКАЗЫВАЛСЯ в поисковиках.

Оставь ТОЛЬКО фразы, которые реальный покупатель мог бы ввести в строку поиска ПО САЙТУ
(товарный/категорийный/брендовый/модельный интент): названия моделей, бренды, типы
оборудования, характеристики («компрессор 10 бар», «винтовой 15 квт»).

УДАЛИ:
- навигационные про сам магазин («прокомпрессор», «компрессор центр», адреса, отзывы о магазине)
- чисто информационные без товарного интента («как работает...», «принцип действия...», «своими руками»)
- запросы с городами, где товарная часть дублирует другую фразу списка
- нерелевантные тематике (автокомпрессоры для шин, аквариумные, медицинские и т.п.)
- мусор и обрывки без смысла

Фразы (по одной на строке):
{phrases}

Ответь ОДНИМ JSON-массивом оставленных фраз (точно в исходном написании): ["...", "..."]"""


def main():
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb.active
    rows = [(r[0], r[2] or 0) for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
    print(f'фраз из вебмастера: {len(rows)}', flush=True)
    client = make_client()
    kept = []
    B = 150
    batches = [rows[i:i + B] for i in range(0, len(rows), B)]

    def worker(idx_batch):
        idx, batch = idx_batch
        prompt = PROMPT.format(phrases='\n'.join(p for p, _ in batch))
        msg = call(client, [{'role': 'user', 'content': prompt}], 'claude-fable-5')
        text = ''.join(b.text for b in msg.content if b.type == 'text')
        m = re.search(r'\[.*\]', text, re.S)
        arr = json.loads(m.group(0))
        shows = dict(batch)
        res = [{'phrase': p, 'shows': shows.get(p, 0), 'source': 'webmaster'} for p in arr if p in shows]
        print(f'батч {idx+1}/{len(batches)}: оставлено {len(res)} из {len(batch)}', flush=True)
        return res

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(worker, (i, b)): i for i, b in enumerate(batches)}
        for f in as_completed(futs):
            try:
                kept += f.result()
            except Exception as e:
                print(f'батч {futs[f]+1} FAIL: {repr(e)[:120]}', flush=True)
    json.dump(kept, open('inventory/keywords-clean.json', 'w'), ensure_ascii=False, indent=1)
    print(f'ИТОГО оставлено: {len(kept)} из {len(rows)}', flush=True)


if __name__ == '__main__':
    main()
