# -*- coding: utf-8 -*-
r"""Отвечает ли луна сейчас: один короткий вызов, без ретраев и без подмены."""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\server')
os.chdir(r'C:\sender\server')
try:
    import gen_provider as GP
except Exception:
    sys.path.insert(0, r'C:\sender\seo-texts')
    import gen_provider as GP

итог = {'base_url': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap'),
        'ключ_есть': bool(os.environ.get('PROVIDER_API_KEY'))}
клиент = GP.make_client()
for модель in ('gpt-5.6-luna', 'gpt-5.6-luna', 'claude-haiku-4-5'):
    t0 = time.time()
    try:
        msg = GP.call(клиент, [{'role': 'user',
                                'content': 'Верни СТРОГО JSON: {"ok": true, "model": "<как тебя зовут>"}'}],
                      model=модель, attempts=1)
        текст = ''.join(getattr(b, 'text', '') for b in getattr(msg, 'content', []))
        u = getattr(msg, 'usage', None)
        итог[модель + '_%d' % len(итог)] = {'итог': 'ОТВЕТИЛА', 'секунд': round(time.time() - t0, 1),
                        'текст': текст.strip()[:60],
                        'вход': getattr(u, 'input_tokens', None),
                        'выход': getattr(u, 'output_tokens', None)}
    except Exception as e:
        итог[модель + '_%d' % len(итог)] = {'итог': 'СБОЙ', 'секунд': round(time.time() - t0, 1),
                        'ошибка': str(e)[:160]}
print(json.dumps(итог, ensure_ascii=False, indent=1))
