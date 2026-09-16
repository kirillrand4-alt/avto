# -*- coding: utf-8 -*-
"""Голый `except: return None` в extract_event превращает ЛЮБОЙ сбой провайдера в «не капекс».
Зову провайдера напрямую и печатаю настоящую ошибку.
"""
import sys, traceback
sys.path.insert(0, r'C:\sender\server')
import news_scan as NS
VC = NS.VC
print('функция: %s' % getattr(VC, '_provider_call_stdlib', None))
for imya, p in (('простой вопрос', 'Ответь одним словом: да'),
                ('короткий JSON', 'Верни строго JSON без markdown: {"ok":true}')):
    print('\n--- %s' % imya)
    try:
        out = VC._provider_call_stdlib(p)
        print('   ответ (%s знаков): %s' % (len(out or ''), str(out)[:300]))
    except Exception as e:
        print('   УПАЛО: %s: %s' % (type(e).__name__, str(e)[:300]))
        traceback.print_exc(limit=3)
