# -*- coding: utf-8 -*-
"""Последние «чужие» вердикты из журнала — глазами, с причинами."""
import io
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
строки = [json.loads(l) for l in io.open(
    r'C:\sender\server\prigovor-domenov.jsonl', encoding='utf-8',
    errors='replace') if l.strip()]
чужие = [r for r in строки if r.get('verdikt') == 'чужой']
print(json.dumps({'чужих_в_журнале': len(чужие), 'последние_10': [
    {'имя': (r.get('name') or '')[:40], 'домен': r.get('домен'),
     'юрлиц': r.get('юрлиц_на_домене'), 'почему': (r.get('pochemu') or '')[:130]}
    for r in чужие[-10:]]}, ensure_ascii=False, indent=1))
