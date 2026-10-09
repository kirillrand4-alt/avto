# Какие модели реально отвечают через шлюз провайдера (короткий вызов каждой); заодно — хватает ли баланса
import json, sys, time
sys.path.insert(0, r'C:\sender\server'); sys.path.insert(0, r'C:\sender')
import verify_company as VC
out = {}
for м in ('claude-fable-5', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5', 'claude-sonnet-4-6', 'claude-sonnet-4-5',
          'claude-haiku-4-5'):
    t = time.time()
    try:
        r = VC._provider_call_stdlib('Ответь одним словом: ок', model=м)
        out[м] = 'ок: %s (%.1f с)' % ((r or '').strip()[:20], time.time() - t)
    except Exception as e:  # noqa: BLE001
        out[м] = 'ошибка: ' + str(e)[:160]
print('===ИТОГ==='); print(json.dumps(out, ensure_ascii=False, indent=0))
