import collections, json
плохих, всего, по = 0, 0, collections.Counter()
for s in open(r'C:\sender\server\ca-glubokiy.jsonl', encoding='utf-8', errors='replace'):
    всего += 1
    try:
        з = json.loads(s)
        по[з.get('inn')] += 1
    except ValueError:
        плохих += 1
print('===ИТОГ===', {'строк': всего, 'битых': плохих, 'компаний': len(по), 'повторов (ИНН >1 раза)': sum(1 for v in по.values() if v > 1)})
