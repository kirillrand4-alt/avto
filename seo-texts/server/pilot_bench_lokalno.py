# -*- coding: utf-8 -*-
"""Сравнение моделей (тот же набор, что pilot_bench_modeli.py), но вызовы — из сессии, не с сервера.
09.10: канал «сервер владельца -> router.cheap» рвёт соединения (WinError 10054), из сессии шлюз отвечает стабильно.
Ключ — PROVIDER_API_KEY окружения сессии (не печатается). Резюм по (модель, id), ответы дописываются в тот же
pilot-bench-otvety.jsonl (потом — на дроп, серверное durable-хранилище).

    python3 pilot_bench_lokalno.py <папка с pilot-bench-nabor.json и pilot-bench-otvety.jsonl> [модель,модель…]
"""
import json
import os
import random
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from pilot_bench_analiz import ЦЕНЫ

ПОТОЛОК = float(os.environ.get('BENCH_POTOLOK', '50'))  # владелец 09.10: «до 50$ сверху ограничение» (весь тест)
ПОРЯДОК = ['claude-opus-5-5', 'claude-sonnet-4-6', 'gpt-6-sol']  # эталон — первым; Fable — последней (самая дорогая)

МОДЕЛИ = ['claude-opus-5-5', 'claude-fable-5', 'claude-sonnet-4-6', 'claude-sonnet-5-5', 'claude-haiku-4-5', 'gpt-6-sol',
          'gpt-6-luna', 'gpt-5.6-luna', 'deepseek-v4-flash', 'deepseek-v4-pro', 'gemini-3.8-flash', 'glm-5.3-flash',
          'qwen3.8-flash', 'grok-4.7', 'minimax-m3', 'mimo-v2.5-pro', 'kimi-k3']
_лок = threading.Lock()


def вызов(модель, промпт):
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    key = os.environ['PROVIDER_API_KEY']
    anth = модель.startswith('claude')
    тело = {'model': модель, 'max_tokens': 2000, 'messages': [{'role': 'user', 'content': промпт}]}
    загол = {'content-type': 'application/json', 'User-Agent': 'curl/8.5.0'}
    if anth:
        загол.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    else:
        загол['Authorization'] = 'Bearer ' + key
    t0 = time.time()
    req = urllib.request.Request(base + ('/v1/messages' if anth else '/v1/chat/completions'),
                                 data=json.dumps(тело, ensure_ascii=False).encode('utf-8'), headers=загол, method='POST')
    д = json.loads(urllib.request.urlopen(req, timeout=300).read())
    u = д.get('usage') or {}
    if anth:
        текст = ''.join(b.get('text', '') for b in д.get('content', []) if b.get('type') == 'text')
        # 09.10: шлюз подмешивает к claude-моделям скрытый системный промпт (~6,7 тыс. токенов) — он идёт как
        # cache_read (дешёвый тариф «Кэш») или как input; считаем раздельно, а итог — по credit_usage шлюза
        вх = u.get('input_tokens') or 0
        кэш = (u.get('cache_read_input_tokens') or 0)
        созд = (u.get('cache_creation_input_tokens') or 0)
        вых = u.get('output_tokens') or 0
    else:
        текст = ((д.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
        вх, вых = u.get('prompt_tokens') or 0, u.get('completion_tokens') or 0
        кэш = ((u.get('prompt_tokens_details') or {}).get('cached_tokens')) or 0
        вх -= кэш
        созд = 0
    return текст, вх, вых, time.time() - t0, кэш, созд, u.get('credit_usage')


КЭШ = {'claude-fable-5': 1, 'claude-opus-5-5': 0.2, 'claude-sonnet-4-6': 0.3, 'claude-sonnet-5-5': 0.2, 'claude-haiku-4-5': 0.1}


def цена(з):
    """$ за вызов: credit_usage шлюза, если есть; иначе — тариф (вход / выход / кэш)."""
    if з.get('кредит'):
        return float(з['кредит'])
    цв, цо = ЦЕНЫ.get(з['модель'], (10, 50))
    return ((з.get('вх') or 0) * цв + (з.get('вых') or 0) * цо + (з.get('кэш') or 0) * КЭШ.get(з['модель'], цв * 0.1)
            + (з.get('кэш_созд') or 0) * цв * 1.25) / 1e6


def main(п, модели=None):
    модели = модели.split(',') if модели else МОДЕЛИ
    задачи = json.load(open(os.path.join(п, 'pilot-bench-nabor.json'), encoding='utf-8'))
    п_отв = os.path.join(п, 'pilot-bench-otvety.jsonl')
    сделано = set()
    потрачено = [0.0]
    for s in open(п_отв, encoding='utf-8'):
        з = json.loads(s)
        if not з.get('ошибка'):
            сделано.add((з['модель'], з['id']))
            потрачено[0] += цена(з)
    работы = [(м, з) for м in модели for з in задачи if (м, з['id']) not in сделано]
    random.shuffle(работы)
    работы.sort(key=lambda x: (0 if x[0] in ПОРЯДОК else 2 if x[0] == 'claude-fable-5' else 1))
    print('вызовов', len(работы), 'уже потрачено $%.2f, потолок $%.0f' % (потрачено[0], ПОТОЛОК), flush=True)
    n = [0]

    def шаг(x):
        м, з = x
        if потрачено[0] >= ПОТОЛОК:
            return
        ош = ''
        for попытка in range(4):
            try:
                текст, вх, вых, сек, кэш, созд, кредит = вызов(м, з['вход'])
                if not текст.strip():
                    raise RuntimeError('пустой ответ')
                з2 = {'модель': м, 'id': з['id'], 'тип': з['тип'], 'ответ': текст, 'вх': вх, 'вых': вых, 'кэш': кэш,
                      'кэш_созд': созд, 'кредит': кредит, 'сек': round(сек, 1), 'вход_символов': len(з['вход']), 'откуда': 'сессия2'}
                with _лок:
                    потрачено[0] += цена(з2)
                break
            except Exception as e:  # noqa: BLE001
                ош = str(e)[:200]
                if hasattr(e, 'read'):
                    ош += ' ' + e.read(200).decode('utf-8', 'replace')
                time.sleep(4 * (попытка + 1))
        else:
            з2 = {'модель': м, 'id': з['id'], 'тип': з['тип'], 'ошибка': ош, 'откуда': 'сессия'}
        with _лок:
            with open(п_отв, 'a', encoding='utf-8') as f:
                f.write(json.dumps(з2, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            n[0] += 1
            if n[0] % 100 == 0:
                print(n[0], 'потрачено $%.2f' % потрачено[0], flush=True)

    with ThreadPoolExecutor(10) as ex:
        list(ex.map(шаг, работы))
    print('готово, потрачено $%.2f' % потрачено[0], flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:3])
