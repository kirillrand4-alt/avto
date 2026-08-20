# -*- coding: utf-8 -*-
r"""Почему луна молчит: это модель, размер промпта или шлюз целиком.

Прогон 10 карточек дал 10 отказов «стрим молчит 95-102с (шлюз шлёт только
ping)» — соединение принято, контент не идёт. Разбираем тремя вопросами:

  1. луна на КОРОТКОМ промпте — жива ли модель вообще;
  2. луна на БОЛЬШОМ (как у паспорта, ~27 тысяч токенов) — дело в размере;
  3. хайку на том же большом — жив ли шлюз и годится ли вторая модель.

Каждый вызов с одной попыткой и коротким ожиданием: диагностика не должна
висеть по пять минут на ретраях.
"""
import json
import os
import sys
import time

for _p in (r'C:\sender', r'C:\sender\server'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import gen_provider as GP  # noqa: E402

КОРОТКИЙ = 'Ответь одним словом: работает.'
# большой промпт делаем из реального текста сайта — синтетический повтор
# одной фразы шлюз мог бы сжать или отбить иначе
def большой():
    import gzip
    KESH = r'C:\seostat\drop\pagecache'
    for n in sorted(os.listdir(KESH))[:40]:
        if not n.endswith('.json.gz'):
            continue
        try:
            with gzip.open(os.path.join(KESH, n), 'rb') as f:
                d = json.loads(f.read().decode('utf-8', 'replace'))
        except Exception:  # noqa: BLE001
            continue
        t = '\n'.join(str((p or {}).get('text') or '')[:8000]
                      for p in (d.get('pages') or []))
        if len(t) > 40000:
            return t[:80000]
    return 'текста не нашлось'


def проба(имя, model, текст, попыток=1):
    t0 = time.time()
    из = {'проба': имя, 'модель': model, 'знаков_в_промпте': len(текст)}
    try:
        klient = GP.make_client()
        msg = GP.call(klient, [{'role': 'user', 'content': текст}],
                      model=model, attempts=попыток)
        u = getattr(msg, 'usage', None)
        из['вход_токенов'] = int(getattr(u, 'input_tokens', 0) or 0)
        из['выход_токенов'] = int(getattr(u, 'output_tokens', 0) or 0)
        из['кэш_чтений'] = int(getattr(u, 'cache_read_input_tokens', 0) or 0)
        из['ответ'] = ''.join(b.text for b in msg.content
                              if getattr(b, 'type', '') == 'text')[:120]
        из['итог'] = 'ОК'
    except Exception as e:  # noqa: BLE001
        из['итог'] = 'СБОЙ'
        из['ошибка'] = str(e)[:220]
    из['секунд'] = round(time.time() - t0, 1)
    return из


текст = большой()
вопрос = ('Вот текст сайта компании. Одним предложением скажи, что компания '
          'производит.\n\n' + текст)
итог = [
    проба('луна, короткий', 'gpt-5.6-luna', КОРОТКИЙ),
    проба('луна, большой', 'gpt-5.6-luna', вопрос),
    проба('хайку, большой', 'claude-haiku-4-5', вопрос),
    проба('хайку, короткий', 'claude-haiku-4-5', КОРОТКИЙ),
]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
print(json.dumps({'КОРОТКО': [{'проба': r['проба'], 'итог': r['итог'],
                               'сек': r['секунд'],
                               'вход': r.get('вход_токенов'),
                               'ошибка': (r.get('ошибка') or '')[:90]}
                              for r in итог]}, ensure_ascii=False))
