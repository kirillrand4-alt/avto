# -*- coding: utf-8 -*-
"""Разбор строк отраслевых референс-листов НЗЛ через провайдера.

Зачем не регуляркой. В компрессорном листе строка идёт «Заказчик Объект Год …», и разбор
по первому году работал. В отраслевых листах порядок другой — «Оборудование Страна Заказчик
Объект Год», и тот же признак выдаёт мусор вида «управления и распределения (НКУ) Россия
Бова…». Это ровно тот класс, где регулярка ломается о разную вёрстку, а модель читает
строку целиком.

Модель обязана отвечать «не знаю»: выдуманный заказчик хуже пропуска.

Использование:
    python3 nzl_razbor.py <nzl-otrasli.csv> <out.csv> [--batch 40] [--threads 15] [--ot 2005]
"""
import csv
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

MODEL = 'claude-fable-5'


def _env():
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

SISTEMA = """Тебе дают строки, вытащенные из PDF-референсов Невского завода — списков
поставленного оборудования за 1947–2020 годы. PDF разбирался автоматически, поэтому поля
в строке слиплись и порядок в разных листах разный: где-то «Заказчик Объект Год», где-то
«Оборудование Страна Заказчик Объект Год Мощность».

По каждой строке верни:
- zakazchik: название предприятия-заказчика, как оно записано в строке. Без страны, без
  типа оборудования, без номера станции.
- obekt: площадка или объект (компрессорная станция, цех, месторождение), если названы
- oborudovanie: что поставлено (турбокомпрессор, ГПА, паровая турбина, НКУ, КТП и т. п.)
- god: год поставки, четыре цифры
- strana: страна заказчика, если названа

Правила, нарушать нельзя:
1. **Ничего не достраивай.** Если поля в строке нет — пустая строка. Выдуманный заказчик
   хуже пропуска: пропуск виден, а выдумка нет.
2. Не превращай обрывок в осмысленное название. «управления и распределения (НКУ)» —
   это хвост типа оборудования, а не заказчик.
3. Никаких пояснений вне JSON.

Ответ — строго JSON-массив объектов с полями n, zakazchik, obekt, oborudovanie, god, strana,
где n — номер строки из входа. Ровно столько элементов, сколько строк на входе."""


def razbor(client, chunk):
    lines = '\n'.join(f'{i}. {t}' for i, t in chunk)
    out = G.call(client, [{'role': 'user', 'content': SISTEMA + '\n\nСтроки:\n' + lines}],
                 model=MODEL)
    txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
    i, j = txt.find('['), txt.rfind(']')
    if i < 0 or j < 0:
        raise ValueError('нет JSON-массива: ' + txt[:150])
    return json.loads(txt[i:j + 1])


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: nzl_razbor.py <in.csv> <out.csv> [--batch N] [--threads N] [--ot ГОД]')
    src, out_path = sys.argv[1], sys.argv[2]
    batch = int(sys.argv[sys.argv.index('--batch') + 1]) if '--batch' in sys.argv else 40
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 15
    ot = sys.argv[sys.argv.index('--ot') + 1] if '--ot' in sys.argv else '0'

    src_rows = [r for r in csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';')
                if r['god_max'] >= ot]
    stroki = [(i, (r['zakazchik'] + ' ' + r['hvost']).strip()[:260])
              for i, r in enumerate(src_rows)]
    print(f'строк к разбору: {len(stroki)} (от {ot} года), потоков {threads}', file=sys.stderr)

    client = G.make_client()
    cols = ['list', 'god_ishodno', 'zakazchik', 'obekt', 'oborudovanie', 'god', 'strana',
            'stroka']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    chunks = [stroki[k:k + batch] for k in range(0, len(stroki), batch)]

    def rabota(nc):
        nomer, chunk = nc
        try:
            return nomer, chunk, razbor(client, chunk)
        except Exception as e:  # noqa: BLE001
            print(f'  партия {nomer}: ОШИБКА {e}', file=sys.stderr)
            return nomer, chunk, []

    done, lock = 0, threading.Lock()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for nomer, chunk, res in pool.map(rabota, enumerate(chunks, 1)):
            by = {}
            for r in res:
                if isinstance(r, dict):
                    try:
                        by[int(r.get('n'))] = r
                    except (TypeError, ValueError):
                        pass
            with lock:
                for i, text in chunk:
                    r = by.get(i) or {}
                    w.writerow({'list': src_rows[i]['list'],
                                'god_ishodno': src_rows[i]['god_max'],
                                'zakazchik': r.get('zakazchik', ''),
                                'obekt': r.get('obekt', ''),
                                'oborudovanie': r.get('oborudovanie', ''),
                                'god': r.get('god', ''), 'strana': r.get('strana', ''),
                                'stroka': text})
                done += len(chunk)
                f.flush()
            print(f'  партия {nomer}/{len(chunks)}: {len(res)} из {len(chunk)}, всего {done}',
                  file=sys.stderr)
    f.close()
    print(f'готово: {done} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
