import io, json, collections
c = collections.Counter(); пуст = 0
for s in io.open(r'C:\sender\server\meyer6-sayt-proverka.jsonl', encoding='utf-8', errors='replace'):
    x = json.loads(s); c[x.get('итог')] += 1
    if not (x.get('шаг1') or {}).get('вердикт'): пуст += 1
print('===ИТОГ==='); print(json.dumps({'итоги': c, 'без вердикта модели': пуст}, ensure_ascii=False))
