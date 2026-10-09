import json, os
print('===ИТОГ==='); print(json.dumps({'PROVIDER_MODEL': os.environ.get('PROVIDER_MODEL', '(не задан → claude-fable-5)'), 'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', '(не задан)'), 'есть_dobor': os.path.exists(r'C:\sender\server\pilot_sayty_dobor.py')}, ensure_ascii=False))
