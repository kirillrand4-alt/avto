# -*- coding: utf-8 -*-
import io, json, collections
к = collections.Counter(); всего = 0
with io.open(r'C:\sender\server\news_stream.jsonl', encoding='utf-8', errors='replace') as f:
    for s in f:
        if '"article_chars"' not in s: continue
        try: d = json.loads(s)
        except Exception: continue
        n = int(d.get('article_chars') or 0); всего += 1
        к['не скачалось' if not n else
          '<2k' if n<2000 else '2k-10k' if n<10000 else 'до 20k (влезает)' if n<20000
          else '20k-50k' if n<50000 else '50k-150k' if n<150000 else '>150k'] += 1
print('===ИТОГ===')
print(json.dumps({'всего': всего, 'корзины': dict(к)}, ensure_ascii=False))
