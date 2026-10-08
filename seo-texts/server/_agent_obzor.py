import io, json
сп = json.load(io.open(r'C:\sender\server\poisk-spisok.json', encoding='utf-8'))['компании']
o = []
for s in io.open(r'C:\sender\server\poisk-glubokiy.jsonl', encoding='utf-8', errors='replace'):
    x = json.loads(s)
    к = сп.get(x['inn'], {})
    o.append('%s | %s | завод: %s [%s] | холдинг: %s [%s] %s | +%d / -%d | %s | %s' % (
        x['inn'], (к.get('имя') or '')[:28], (x.get('сайт_завода') or '')[:30], (x.get('сайт_завода_чей') or '')[:20],
        (x.get('холдинг') or '')[:20], 'подтв' if x.get('холдинг_подтверждён') else '-', (x.get('сайт_холдинга') or '')[:25],
        len(x.get('номера') or []), len(x.get('снято') or []),
        '; '.join(sorted({н.get('причина', '')[:30] for н in x.get('снято') or []}))[:80], (x.get('пояснение') or '')[:120]))
print('===ИТОГ==='); print('\n'.join(o)[-6000:])
