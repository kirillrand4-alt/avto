# Какие модели отдаёт шлюз провайдера (GET /v1/models); ключ не печатается
import json, os, urllib.request
base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
key = os.environ.get('PROVIDER_API_KEY', '')
out = {}
for путь, загол in (('/v1/models', {'Authorization': 'Bearer ' + key}), ('/v1/models', {'x-api-key': key, 'anthropic-version': '2023-06-01'})):
    try:
        req = urllib.request.Request(base + путь, headers=dict(загол, **{'User-Agent': 'curl/8.5.0'}))
        d = json.loads(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=40).read())
        out['модели'] = sorted({m.get('id') for m in d.get('data', []) if m.get('id')})
        break
    except Exception as e:  # noqa: BLE001
        out.setdefault('ошибки', []).append(repr(e)[:120])
print('===ИТОГ==='); print(json.dumps(out, ensure_ascii=False))
