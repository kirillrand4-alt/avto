# -*- coding: utf-8 -*-
"""Разведка перед выкачкой: сколько страниц ТУ у каждого ИНН в реестре ЭПБ.

Один запрос на предприятие. Нужна, чтобы не уйти в 279 страниц на гигантах вслепую.

Пишет ПОСТРОЧНО в jsonl и продолжает с места остановки: три прошлых запуска умерли молча
(процесс убит вместе с оболочкой), и каждый раз терялся весь час работы, потому что итог
писался одним куском в конце.
"""
import json, os, re, sys, time
sys.path.insert(0, '/home/user/avto/seo-texts')
import mpb_po_inn as M
from concurrent.futures import ThreadPoolExecutor

POTOK = 'epb-razvedka.jsonl'
inns = [x.strip() for x in open('inn-vse-celi.txt') if x.strip()]
gotovo = set()
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            gotovo.add(json.loads(ln)['inn'])
        except Exception:
            pass
ostalos = [i for i in inns if i not in gotovo]
print(f'всего {len(inns)}, уже сделано {len(gotovo)}, осталось {len(ostalos)}',
      file=sys.stderr, flush=True)

f = open(POTOK, 'a', encoding='utf-8')


def one(inn):
    url = f'{M.BAZA}/conclusions?exploiter={inn}&type=%D0%A2%D0%A3'
    h = M._vzyat(url, popytok=2)
    if h.startswith('__ОШИБКА__'):
        return {'inn': inn, 'stranic': -1, 'na_stranice': 0, 'imya': '', 'err': h[:80]}
    st = [int(x) for x in
          re.findall(r'href="/conclusions\?[^"]*exploiter=%s[^"]*page=(\d+)' % inn, h)]
    rows = M._stroki(h)
    return {'inn': inn, 'stranic': (max(st) if st else (1 if rows else 0)),
            'na_stranice': len(rows), 'imya': rows[0]['zakazchik'] if rows else '', 'err': ''}


n = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    for r in ex.map(one, ostalos):
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
        n += 1
        if n % 100 == 0:
            f.flush()
            os.fsync(f.fileno())
            print(f'  {n}/{len(ostalos)}', file=sys.stderr, flush=True)
f.flush()
f.close()

rez = [json.loads(l) for l in open(POTOK, encoding='utf-8') if l.strip()]
est = [r for r in rez if r['stranic'] > 0]
sboi = [r for r in rez if r['stranic'] < 0]
print(f'всего ИНН {len(rez)} | есть заключения ТУ: {len(est)} | '
      f'нет: {len(rez)-len(est)-len(sboi)} | сбоев: {len(sboi)}', file=sys.stderr)
print(f'суммарно страниц: {sum(r["stranic"] for r in est)} '
      f'(это ~{sum(r["stranic"] for r in est)*25} заключений)', file=sys.stderr)
print('топ по объёму:', file=sys.stderr)
for r in sorted(est, key=lambda x: -x['stranic'])[:15]:
    print(f'  {r["stranic"]:>4} стр  {r["inn"]}  {r["imya"][:48]}', file=sys.stderr)
