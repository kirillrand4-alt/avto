import json, sys, time
sys.path.insert(0, r'C:\sender\server'); sys.path.insert(0, r'C:\sender')
import verify_company as VC
out = []
for м in ('gpt-6-luna', 'gpt-6-sol', 'gpt-6-luna', 'gpt-6-luna'):
    t = time.time()
    try:
        r = VC._provider_call_stdlib('Ответь одним словом: ок', model=м)
        out.append('%s ок %r %.1fс' % (м, (r or '')[:10], time.time() - t))
    except Exception as e:
        out.append('%s ошибка %s' % (м, str(e)[:100]))
print('===ИТОГ==='); print(json.dumps(out, ensure_ascii=False))
