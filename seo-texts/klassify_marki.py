# -*- coding: utf-8 -*-
"""Определение типа машины и рабочей среды по марке — через провайдера.

Зачем. В `epb-centro-vse.csv` у 3 548 строк из 7 750 среда в тексте объекта **не названа**:
стоит только обозначение, «компрессор центробежный К-500-61-1 поз. 1/4». Регулярка про
такие строки не знает ничего, поэтому оценка «212 предприятий с воздушными машинами» —
заведомо нижняя. Марка при этом среду задаёт однозначно: К-500-61-1 — воздушный
турбокомпрессор, 4ГЦ2-184/13,5-76 — газовый.

Классифицируются **различные обозначения**, а не строки: обозначений 1 535 на 3 548 строк,
то есть работы вдвое меньше, а результат переносится на все строки с той же маркой.

Модель обязана отвечать «не знаю» — выдуманная расшифровка марки хуже пропуска, потому что
пропуск виден, а выдумка нет. В ответе есть поле `uverennost`, и всё, что ниже «высокая»,
в чистый воздушный список не идёт.

Использование:
    python3 klassify_marki.py <marki.txt> <out.csv> [--batch 60]
"""
import csv
import json
import os
import sys
import time

import gen_provider as G

MODEL = 'claude-fable-5'


def _env():
    """Креды из окружения, а не из .env — файла в песочнице нет (как в lens_centro.py)."""
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

SISTEMA = """Ты инженер по компрессорному оборудованию. Тебе дают обозначения, выдернутые
из текстов заключений экспертизы промышленной безопасности российских предприятий, и по
каждому — реальные строки реестра, в которых оно встретилось. Часть обозначений — марки
машин, часть — мусор: номера регистрации, позиции по схеме, названия площадок и цехов.

По каждому обозначению верни:
- tip: центробежный | поршневой | винтовой | турбодетандер | вентилятор | насос | не машина | не знаю
- sreda: воздух | природный газ | технологический газ | азот | кислород | аммиак | водород | холодильный агент | не знаю
- rasshifrovka: одна короткая строка, что это за машина (или почему это не машина)
- uverennost: высокая | средняя | низкая

Правила, нарушать нельзя:
1. **Опирайся на приведённые строки реестра, а не на догадку по виду обозначения.**
   Если строки среду не выдают и уверенного знания у тебя нет — ставь «не знаю» и
   уверенность «низкая». Выдуманная расшифровка хуже пропуска: пропуск виден, а
   выдумка нет.
2. Уверенность «высокая» ставится только тогда, когда среда следует из самих строк или
   из твёрдого знания конкретной марки. Общее правило по букве серии твёрдым знанием
   НЕ является: в одной серии бывают исполнения на разные среды.
3. Обозначения вида «КЦ-101/2», «ГПП-1», «ТЭЦ-1», «П-4/2», «А68-00341-0076» —
   это номера цехов, площадок, позиций и регистрации, а не марки. tip = «не машина».
4. Никаких пояснений вне JSON.

Ответ — строго JSON-массив объектов с полями oboznachenie, tip, sreda, rasshifrovka,
uverennost. Ровно столько элементов, сколько обозначений на входе, в том же порядке."""


def klassify(client, marki, primery=None):
    primery = primery or {}
    lines = []
    for i, m in enumerate(marki):
        lines.append(f'{i+1}. {m}')
        for p in (primery.get(m) or [])[:3]:
            lines.append(f'     строка реестра: {p[:190]}')
    msg = [{'role': 'user', 'content': 'Обозначения и строки, где они встретились:\n'
            + '\n'.join(lines)}]
    out = G.call(client, [{'role': 'user', 'content': SISTEMA + '\n\n' + msg[0]['content']}],
                 model=MODEL)
    # call() возвращает объект-сообщение: текст лежит в блоках content, а не в str(out)
    txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
    i, j = txt.find('['), txt.rfind(']')
    if i < 0 or j < 0:
        raise ValueError('в ответе нет JSON-массива: ' + txt[:200])
    return json.loads(txt[i:j + 1])


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: klassify_marki.py <marki.txt> <out.csv> [--batch N]')
    marki_path, out_path = sys.argv[1], sys.argv[2]
    batch = 60
    if '--batch' in sys.argv:
        batch = int(sys.argv[sys.argv.index('--batch') + 1])

    marki = [l.strip() for l in open(marki_path, encoding='utf-8') if l.strip()]
    print(f'обозначений: {len(marki)}, партий по {batch}', file=sys.stderr)

    # Строки-примеры: берутся ТОЛЬКО из строк без названной среды — тех самых, ради
    # которых всё и делается. Иначе на обозначениях, у которых среда где-то названа
    # явно, ответ утёк бы во вход и замер точности перестал быть слепым.
    primery = {}
    if '--primery' in sys.argv:
        primery = json.load(open(sys.argv[sys.argv.index('--primery') + 1], encoding='utf-8'))
        print(f'примеров подгружено для {len(primery)} обозначений', file=sys.stderr)

    client = G.make_client()
    cols = ['oboznachenie', 'tip', 'sreda', 'rasshifrovka', 'uverennost']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    done = 0
    for k in range(0, len(marki), batch):
        chunk = marki[k:k + batch]
        try:
            res = klassify(client, chunk, primery)
        except Exception as e:  # noqa: BLE001
            print(f'  партия {k // batch + 1}: ОШИБКА {e}', file=sys.stderr)
            time.sleep(3)
            continue
        # выравнивание по порядку: модель может вернуть меньше/больше
        by = {str(r.get('oboznachenie', '')).strip(): r for r in res if isinstance(r, dict)}
        for m in chunk:
            r = by.get(m) or {}
            w.writerow({'oboznachenie': m,
                        'tip': r.get('tip', 'не знаю'),
                        'sreda': r.get('sreda', 'не знаю'),
                        'rasshifrovka': r.get('rasshifrovka', ''),
                        'uverennost': r.get('uverennost', 'низкая')})
        done += len(chunk)
        f.flush()
        print(f'  партия {k // batch + 1}: получено {len(res)} из {len(chunk)}, всего {done}',
              file=sys.stderr)

    f.close()
    print(f'готово: {done} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
