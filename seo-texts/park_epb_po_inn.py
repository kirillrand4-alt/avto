# -*- coding: utf-8 -*-
"""Полный список заключений ЭПБ по каждому ИНН — вглубь, а не вширь.

Широкий проход по словам находит ПРЕДПРИЯТИЯ. Этот берёт по каждому найденному ИНН ВСЕ его
заключения: `/conclusions?exploiter=<ИНН>&type=ТУ`, до 400 страниц. У ПАО «Химпром» их 279,
то есть около 7 000 заключений против 10 на карточке — карточка показывает только последние.

Идёт параллельно ширине: это разные адреса реестра и разные ответы.
"""
import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpb_po_inn as M

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
POTOK = os.path.join(L, 'PARK-EPB-PO-INN-2S.jsonl')
POTOK_SHIR = os.path.join(L, 'PARK-EPB-SHIROKIY-2S.jsonl')
FAKTY = os.path.join(L, 'PARK-FAKTY-2S-EPB.csv')
NITEY = int(os.environ.get('NITEY', '4'))
PREDEL = int(os.environ.get('PREDEL', '400'))


def celi():
    import csv
    csv.field_size_limit(10 ** 7)
    est = set()
    if os.path.exists(FAKTY):
        est = {r['inn'] for r in csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';')}
    novye = set()
    if os.path.exists(POTOK_SHIR):
        for ln in open(POTOK_SHIR, encoding='utf-8'):
            try:
                for r in (json.loads(ln).get('stroki') or []):
                    novye.add(r['inn'])
            except json.JSONDecodeError:
                pass
    # НОВЫЕ ВПЕРЁД: по ним у нас нет ничего, а по старым уже есть 20 830 фактов.
    return [i for i in novye if i not in est] + sorted(est)


def main():
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                gotovo.add(json.loads(ln)['inn'])
            except (json.JSONDecodeError, KeyError):
                pass
    zadanie = [i for i in celi() if i not in gotovo]
    print(f'целей {len(zadanie)}, уже пройдено {len(gotovo)}', file=sys.stderr, flush=True)
    if not zadanie:
        return
    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'ИНН': 0, 'строк': 0, 'ошибок': 0}

    def odin(inn):
        stroki, err = M.po_inn(inn, max_stranic=PREDEL, tolko_tu=True)
        with lock:
            sch['ИНН'] += 1
            sch['строк'] += len(stroki)
            if err:
                sch['ошибок'] += 1
            f.write(json.dumps({'inn': inn, 'err': (err or '')[:70],
                                'stroki': stroki}, ensure_ascii=False) + '\n')
            f.flush()
            if sch['ИНН'] % 10 == 0:
                print(f"  {sch['ИНН']}/{len(zadanie)}: строк {sch['строк']}, ошибок {sch['ошибок']}",
                      file=sys.stderr, flush=True)
        time.sleep(0.8)

    with ThreadPoolExecutor(max_workers=NITEY) as p:
        list(p.map(odin, zadanie))
    print(f"готово: {sch}", file=sys.stderr)


main()
