# -*- coding: utf-8 -*-
"""Насколько свежи события xmlriver: годы в тексте и в ссылках."""
import io, json, re, collections

годы = collections.Counter()
годы_ссылок = collections.Counter()
примеры_старых = []
события = []
with io.open(r'C:\sender\server\news_stream.jsonl', encoding='utf-8', errors='replace') as f:
    n = 0
    for s in f:
        n += 1
        if n <= 5270 or 'xmlriver' not in s[:400]:
            continue
        try:
            события.append(json.loads(s))
        except Exception:
            pass
for d in события:
    т = ' '.join(str(d.get(k) or '') for k in ('what', 'title'))
    г = re.findall(r'\b(20[12]\d)\b', т)
    годы.update(г or ['(года нет в тексте)'])
    u = str(d.get('source_url') or '')
    гu = re.findall(r'/(20[12]\d)/', u)
    годы_ссылок.update(гu or ['(нет в ссылке)'])
    if any(x in ('2021', '2022', '2023', '2024') for x in г) and len(примеры_старых) < 5:
        примеры_старых.append({'кто': str(d.get('company'))[:32],
                               'что': т[:90], 'ссылка': u[:60]})
print('===ИТОГ===')
print(json.dumps({'событий': len(события),
                  'годы_в_тексте': годы.most_common(8),
                  'годы_в_ссылке': годы_ссылок.most_common(6),
                  'примеры_старых': примеры_старых},
                 ensure_ascii=False, indent=1))
