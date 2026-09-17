# -*- coding: utf-8 -*-
"""Не скачиваем ли мы вместо статьи ленту издания: распределение article_chars."""
import io, json, collections

корзины = collections.Counter()
большие = []
всего = с_текстом = 0
with io.open(r'C:\sender\server\news_stream.jsonl', encoding='utf-8', errors='replace') as f:
    for s in f:
        if '"article_chars"' not in s:
            continue
        try:
            d = json.loads(s)
        except Exception:
            continue
        n = int(d.get('article_chars') or 0)
        всего += 1
        if not n:
            корзины['0 (не скачалось)'] += 1
            continue
        с_текстом += 1
        if n < 2000: корзины['<2k'] += 1
        elif n < 10000: корзины['2k-10k'] += 1
        elif n < 20000: корзины['10k-20k (влезает целиком)'] += 1
        elif n < 50000: корзины['20k-50k (обрезано)'] += 1
        elif n < 150000: корзины['50k-150k (похоже на ленту)'] += 1
        else: корзины['>150k (точно не статья)'] += 1
        if n > 50000 and len(большие) < 6:
            большие.append({'знаков': n, 'источник': d.get('source_name'),
                            'что': str(d.get('what'))[:60],
                            'ссылка': str(d.get('source_url'))[:60]})
print('===ИТОГ===')
print(json.dumps({'записей_с_полем': всего, 'скачалось': с_текстом,
                  'корзины': корзины.most_common(),
                  'примеры_больших': большие[:1]}, ensure_ascii=False, indent=1)[:3500])
