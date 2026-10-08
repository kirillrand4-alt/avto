import sys, json
sys.path.insert(0, r'C:\sender\server'); sys.path.insert(0, r'C:\sender')
import verify_company as VC
try:
    out = VC._provider_call_stdlib('Ответь одним словом: ok')
except Exception as e:
    out = 'ОШИБКА ' + repr(e)[:200]
print('===ИТОГ==='); print(json.dumps({'ответ': (out or 'None')[:200]}, ensure_ascii=False))
