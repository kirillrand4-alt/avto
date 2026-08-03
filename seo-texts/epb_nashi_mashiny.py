# -*- coding: utf-8 -*-
"""Наши машины и сроки их ЭПБ по всем предприятиям базы — дешёвым запросом.

Разведка показала: заключения на технические устройства есть у 1 061 предприятия из 1 853,
суммарно 79 057 страниц, около двух миллионов заключений. Качать всё — сутки работы ради
горсти компрессоров. Узкий запрос `q=<слово>&exploiter=<ИНН>&type=ТУ` даёт то же самое за
одну-две страницы на предприятие.

Пишет построчно и продолжает с места остановки: прогон на несколько часов, а терять его
целиком из-за обрыва нельзя.
"""
import csv, json, os, sys, time
sys.path.insert(0, '/home/user/avto/seo-texts')
import mpb_po_inn as M
from concurrent.futures import ThreadPoolExecutor

POTOK = 'epb-nashi-potok.jsonl'
razv = [json.loads(l) for l in open('epb-razvedka.jsonl', encoding='utf-8') if l.strip()]
celi = [r['inn'] for r in razv if r['stranic'] > 0]
gotovo = set()
if os.path.exists(POTOK):
    for l in open(POTOK, encoding='utf-8'):
        try:
            gotovo.add(json.loads(l)['inn'])
        except Exception:
            pass
ost = [i for i in celi if i not in gotovo]
print(f'предприятий с заключениями ТУ: {len(celi)}, сделано {len(gotovo)}, осталось {len(ost)}',
      file=sys.stderr, flush=True)

f = open(POTOK, 'a', encoding='utf-8')
M.PAUZA = 0.3


# СРОКИ ЗДЕСЬ НЕ БЕРУТСЯ, и это замер, а не лень. Реестр отвечает около 5 с на запрос;
# пять ключевых слов на предприятие — это уже 25 с, а добор сроков внутри того же цикла
# поднимал по четыре соединения на каждый из шести рабочих потоков, реестр начинал
# придерживать, и общий ход падал до полутора предприятий в минуту (двенадцать часов на
# 1 061). Сроки — вторым проходом и ТОЛЬКО по центробежным строкам: их сотни, а не
# десятки тысяч. См. `epb_sroki.py`.
def one(inn):
    rows, err = M.po_inn_slova(inn)
    return {'inn': inn, 'err': err, 'rows': rows}


n = 0
with ThreadPoolExecutor(max_workers=12) as ex:
    for r in ex.map(one, ost):
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
        n += 1
        if n % 25 == 0:
            f.flush(); os.fsync(f.fileno())
            print(f'  {n}/{len(ost)}', file=sys.stderr, flush=True)
f.flush(); f.close()

vse = [json.loads(l) for l in open(POTOK, encoding='utf-8') if l.strip()]
kol = ['inn', 'predpriyatie', 'nomer', 'data', 'obekt', 'tip', 'tip_rasshifrovka',
       'ekspertnaya_org', 'inn_eo', 'vyvod', 'deystvuet_do', 'status', 'nashli_po',
       'nashe_oborudovanie', 'centrobezhnoe', 'nasos', 'ne_mashina', 'ssylka']
strok = centro = nashi = istyok = 0
predpr_centro = set()
with open('EPB-NASHI-MASHINY.csv', 'w', encoding='utf-8-sig', newline='') as g:
    w = csv.DictWriter(g, fieldnames=kol, delimiter=';', extrasaction='ignore')
    w.writeheader()
    for z in vse:
        for r in z.get('rows') or []:
            w.writerow(r); strok += 1
            if r['centrobezhnoe']:
                centro += 1; predpr_centro.add(r['inn'])
            if r['nashe_oborudovanie']:
                nashi += 1
            if 'ист' in (r.get('status') or ''):
                istyok += 1
sboi = [z for z in vse if z.get('err')]
print(f'строк {strok} | наших машин {nashi} | ЦЕНТРОБЕЖНЫХ {centro} у {len(predpr_centro)} '
      f'предприятий | с истёкшей ЭПБ {istyok} | СБОЕВ {len(sboi)}', file=sys.stderr)
