# -*- coding: utf-8 -*-
"""Журнал вызовов ключа провайдера по моделям (09.10). Шлюз отдаёт /api/log/token — последние 1 000 вызовов ключа
(модель, quota, токены, время). Ключом пользуются и другие сессии владельца, поэтому общий счётчик не годится как
лимит шага; журнал по моделям даёт точную цену моделей, которыми чужие сессии не пользуются (09.10: gpt-6-luna,
gpt-5.6-luna), а для общих (gpt-6-sol) — разницу с фоном.

    python3 _zhurnal_provider.py копить <файл.jsonl> [сек]      # фоновый сбор, без дублей (по request_id)
    python3 _zhurnal_provider.py итог <файл.jsonl> <с unix-времени> [по unix-время]
Запуск ИЗ СЕССИИ (ключ в окружении). Ключ не печатается. $1 = 500 000 quota (New API).
"""
import collections
import json
import os
import sys
import time
import urllib.request

QUOTA_USD = 500000.0


def журнал():
    б = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    з = urllib.request.Request(б + '/api/log/token', headers={
        'Authorization': 'Bearer ' + os.environ['PROVIDER_API_KEY'], 'User-Agent': 'curl/8.5.0'})
    return json.loads(urllib.request.urlopen(з, timeout=60).read())['data']


def ключ(x):
    return x.get('request_id') or '%s|%s|%s|%s' % (x['created_at'], x['model_name'], x['quota'], x.get('prompt_tokens'))


def копить(путь, пауза=60):
    видел = set()
    if os.path.exists(путь):
        for s in open(путь, encoding='utf-8'):
            try:
                видел.add(json.loads(s)['k'])
            except (ValueError, KeyError):
                pass
    while True:
        try:
            новые = []
            записей = журнал()
            for x in записей:
                k = ключ(x)
                if k not in видел:
                    видел.add(k)
                    новые.append({'k': k, 't': x['created_at'], 'm': x['model_name'], 'q': x['quota'], 'type': x.get('type'),
                                  'in': x.get('prompt_tokens'), 'out': x.get('completion_tokens')})
            with open(путь, 'a', encoding='utf-8') as f:
                for н in sorted(новые, key=lambda н: н['t']):
                    f.write(json.dumps(н, ensure_ascii=False) + '\n')
            # все 1 000 — новые: окно журнала переполнено между опросами, часть вызовов потеряна
            if записей and len(новые) == len(записей) and len(видел) > len(записей):
                with open(путь + '.warn', 'a', encoding='utf-8') as f:
                    f.write('%s переполнение окна\n' % time.strftime('%H:%M:%S'))
        except Exception as e:  # noqa: BLE001
            with open(путь + '.warn', 'a', encoding='utf-8') as f:
                f.write('%s %r\n' % (time.strftime('%H:%M:%S'), e))
        time.sleep(пауза)


def итог(путь, с, по=None):
    м = collections.defaultdict(lambda: [0, 0.0])
    for s in open(путь, encoding='utf-8'):
        x = json.loads(s)
        if x['t'] >= с and (по is None or x['t'] <= по):
            м[x['m']][0] += 1
            м[x['m']][1] += x['q'] / QUOTA_USD
    for модель, (n, usd) in sorted(м.items(), key=lambda t: -t[1][1]):
        print('%-22s вызовов %6d  $%.2f' % (модель, n, usd))
    print('всего $%.2f' % sum(v[1] for v in м.values()))


if __name__ == '__main__':
    if sys.argv[1] == 'копить':
        копить(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 60)
    else:
        итог(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else None)
