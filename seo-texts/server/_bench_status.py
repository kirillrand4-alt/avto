import collections, io, json, os
п = r'C:\sender\server\pilot-bench-otvety.jsonl'
с = collections.Counter(); ош = collections.Counter(); пр = {}
if os.path.exists(п):
    for s in io.open(п, encoding='utf-8', errors='replace'):
        з = json.loads(s)
        if з.get('ошибка'):
            ош[з['модель']] += 1; пр[з['модель']] = з['ошибка'][:120]
        else:
            с[з['модель']] += 1
лог = sorted(f for f in os.listdir(r'C:\sender\server') if f.startswith('pilot_bench_'))[-1:]
print('===ИТОГ==='); print(json.dumps({'ok': dict(с), 'ошибки': dict(ош), 'пример ошибки': пр,
      'лог': open(os.path.join(r'C:\sender\server', лог[0]), encoding='utf-8', errors='replace').read()[-300:] if лог else ''}, ensure_ascii=False, indent=0))
