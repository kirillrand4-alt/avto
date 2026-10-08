import io, os, time, json
п = r'C:\sender\server\meyer6-glubokiy2.jsonl'
n = sum(1 for _ in io.open(п, encoding='utf-8', errors='replace')) if os.path.exists(п) else 0
print('===ИТОГ==='); print(time.strftime('%H:%M'), 'перепроверено', n, 'из', sum(1 for _ in io.open(r'C:\sender\server\meyer6-glubokiy.jsonl', encoding='utf-8', errors='replace')))
