# -*- coding: utf-8 -*-
"""Запасной канал к провайдеру: Gemini и GPT через OpenAI-совместимый путь.

ЗАЧЕМ. Владелец: «по провайдеру если рвётся, можешь взять модели другие типа гемини».
Проверил — просто подставить имя модели в `gen_provider.call` НЕЛЬЗЯ: он ходит на
`/v1/messages` (нативный anthropic-путь), и провайдер отвечает
`HTTP 503 No available channel for model gemini-3.6-flash under group default`.
В таблице провайдера у Claude стоит совместимость «anthropic», а у Gemini и GPT — «openai».
Значит их зовут другим адресом: `/v1/chat/completions`. Проверено живьём, отвечают все
четыре: gemini-3.6-flash, gemini-3.5-flash, gpt-5.6-luna, gpt-5.4-mini.

Заголовок `User-Agent: curl/8.5.0` тот же, что в `gen_provider`: WAF самого шлюза отклоняет
дефолтные заголовки SDK.
"""
import os, sys, time
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

# Порядок = порядок отката. Первым штатная модель, дальше дешёвые запасные.
CEPOCHKA = ['claude-fable-5', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gpt-5.4-mini']


def sprosit(soobshcheniya, modeli=None, max_tokens=8000, popytok=2):
    """→ (текст, какой моделью). Перебирает цепочку: порвалась одна — идёт следующая."""
    e = G.env()
    baza = e['PROVIDER_BASE_URL'].rstrip('/')
    posl = None
    for model in (modeli or CEPOCHKA):
        for p in range(popytok):
            try:
                if model.startswith('claude'):
                    msg = G.call(None, soobshcheniya, model=model, attempts=1)
                    t = ''.join(b.text for b in msg.content if b.type == 'text')
                else:
                    h = {'Content-Type': 'application/json',
                         'Authorization': 'Bearer ' + e['PROVIDER_API_KEY'],
                         'User-Agent': 'curl/8.5.0'}
                    r = httpx.post(baza + '/v1/chat/completions', headers=h, timeout=300.0,
                                   json={'model': model, 'messages': soobshcheniya,
                                         'max_tokens': max_tokens, 'stream': False})
                    r.raise_for_status()
                    t = (r.json().get('choices') or [{}])[0].get('message', {}).get('content', '')
                if (t or '').strip():
                    return t, model
                posl = 'пустой ответ'
            except Exception as ex:  # noqa: BLE001
                posl = f'{model}: {str(ex)[:110]}'
                time.sleep(2 + 3 * p)
    raise RuntimeError('вся цепочка моделей не ответила, последнее: ' + str(posl))


if __name__ == '__main__':
    t, m = sprosit([{'role': 'user', 'content': 'Ответь одним словом: работает?'}])
    print(f'{m} → {t[:60]}')
