import io, json, os
п = r'C:\sender\server\cc-checko.jsonl'
стр = [json.loads(s) for s in io.open(п, encoding='utf-8', errors='replace')]
print('===ИТОГ===')
for з in стр[-6:]:
    print(json.dumps({k: str(v)[:160] for k, v in з.items() if k not in ('target_codes_found', 'secondary_28x_info')}, ensure_ascii=False))
