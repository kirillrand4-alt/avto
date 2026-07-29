# -*- coding: utf-8 -*-
"""Сведение советских названий предприятий к нынешним — через провайдера.

Зачем. В референс-листе Невского завода 475 заказчиков за 1947–2019, и сопоставление по
строке даёт всего 9 совпадений с нашими 347 предприятиями. Причина не в том, что заводов
нет, а в том, что **советские названия не совпадают с современными юрлицами**: «Кузнецкий
МК» — это сегодняшний ЕВРАЗ ЗСМК, «Томский НХК» — ООО «Томскнефтехим». Вручную в выборке
из 20 нашлось три таких случая. Регулярка этого не умеет, модель умеет.

**ИНН у модели не спрашивается вообще.** Идентификатор, который модель не может проверить,
она выдумает, и выдумка будет выглядеть правдоподобно — это ровно та ошибка, на которой
попался склеенный телефон (ловушка В11). Модель отдаёт только современное название и
страну; ИНН подставляется **из наших собственных данных** поиском по названию, поэтому
несуществующий ИНН появиться не может физически.

Использование:
    python3 svesti_nazvaniya.py <zakazchiki.json> <out.csv> [--batch 25] [--threads 15]
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

SISTEMA = """Тебе дают названия предприятий из референс-листа поставок компрессорного
оборудования Невского завода за 1947–2019 годы. Названия записаны так, как их писали на
момент поставки: советские сокращения, отраслевые аббревиатуры, ведомства.

По каждому названию верни:
- sovremennoe: как это предприятие называется сейчас, полным современным названием
  (например «Кузнецкий МК» -> «ЕВРАЗ Западно-Сибирский металлургический комбинат»)
- strana: Россия | Украина | Казахстан | Узбекистан | Белоруссия | другая | не знаю
- sostoyanie: работает | закрыто | вошло в состав другого | ведомство упразднено | не знаю
- uverennost: высокая | средняя | низкая

Правила, нарушать нельзя:
1. **ИНН, адресов, телефонов и сайтов не называть ни при каких условиях.** Их у тебя нет,
   а выдуманный идентификатор выглядит правдоподобно и потому опаснее пропуска.
2. Если не знаешь — «не знаю» и уверенность «низкая». Не угадывай по созвучию.
3. Многие предприятия остались за границей после 1991 года. Это нормальный ответ,
   помечай страной; не пытайся подобрать российский аналог.
4. Родовые имена («Азот», «Газпром», ведомства вроде «Мингазпром СССР») — это не одно
   предприятие. Ставь sostoyanie = «не знаю» и поясняй в sovremennoe, что имя родовое.
5. Никаких пояснений вне JSON.

Ответ — строго JSON-массив объектов с полями nazvanie, sovremennoe, strana, sostoyanie,
uverennost. Ровно столько элементов, сколько названий на входе."""


def svesti(client, batch):
    lines = []
    for i, d in enumerate(batch, 1):
        lines.append(f"{i}. {d['nazvanie']} | поставок {d['postavok']} | годы {d['gody']}"
                     f" | объект: {d['obekt']}")
    out = G.call(client, [{'role': 'user', 'content': SISTEMA + '\n\nНазвания:\n'
                           + '\n'.join(lines)}], model=MODEL)
    txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
    i, j = txt.find('['), txt.rfind(']')
    if i < 0 or j < 0:
        raise ValueError('в ответе нет JSON-массива: ' + txt[:200])
    return json.loads(txt[i:j + 1])


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: svesti_nazvaniya.py <zakazchiki.json> <out.csv> '
                 '[--batch N] [--threads N]')
    src, out_path = sys.argv[1], sys.argv[2]
    batch = 25
    if '--batch' in sys.argv:
        batch = int(sys.argv[sys.argv.index('--batch') + 1])
    threads = 1
    if '--threads' in sys.argv:
        threads = int(sys.argv[sys.argv.index('--threads') + 1])

    items = json.load(open(src, encoding='utf-8'))
    print(f'названий: {len(items)}, партий по {batch}, потоков {threads}', file=sys.stderr)

    client = G.make_client()
    cols = ['nazvanie', 'postavok', 'gody', 'sovremennoe', 'strana', 'sostoyanie', 'uverennost']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    chunks = [items[k:k + batch] for k in range(0, len(items), batch)]

    def rabota(nc):
        nomer, chunk = nc
        try:
            return nomer, chunk, svesti(client, chunk)
        except Exception as e:  # noqa: BLE001
            print(f'  партия {nomer}: ОШИБКА {e}', file=sys.stderr)
            return nomer, chunk, []

    done, lock = 0, threading.Lock()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for nomer, chunk, res in pool.map(rabota, enumerate(chunks, 1)):
            by = {str(r.get('nazvanie', '')).strip(): r for r in res if isinstance(r, dict)}
            with lock:
                for d in chunk:
                    r = by.get(d['nazvanie']) or {}
                    w.writerow({'nazvanie': d['nazvanie'], 'postavok': d['postavok'],
                                'gody': d['gody'],
                                'sovremennoe': r.get('sovremennoe', ''),
                                'strana': r.get('strana', 'не знаю'),
                                'sostoyanie': r.get('sostoyanie', 'не знаю'),
                                'uverennost': r.get('uverennost', 'низкая')})
                done += len(chunk)
                f.flush()
            print(f'  партия {nomer}/{len(chunks)}: получено {len(res)} из {len(chunk)}, '
                  f'всего {done}', file=sys.stderr)

    f.close()
    print(f'готово: {done} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
