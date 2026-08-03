# -*- coding: utf-8 -*-
"""Второй проход по ЭПБ: срок и статус экспертизы — только по нашим машинам.

ПОЧЕМУ ОТДЕЛЬНЫМ ПРОХОДОМ. Реестр отвечает около пяти секунд на запрос. Сбор машин уже
тратит по пять запросов на предприятие, и добор сроков внутри того же цикла поднимал ещё
по четыре соединения на каждый рабочий поток — реестр начинал придерживать, и общий ход
падал до полутора предприятий в минуту, то есть двенадцать часов на 1 061 предприятие.

Здесь сроки берутся уже по готовому файлу и ТОЛЬКО по строкам, где стоит `centrobezhnoe`
или `nashe_oborudovanie`. Таких строк сотни, а не десятки тысяч.

Срок — главный сигнал момента: у машины кончается экспертиза, значит её либо продлевают,
либо меняют. Формулировок в карточке две, и обе учтены: «Действует до 05.06.2031» и
«Срок истёк 31.12.2022». Просроченные и есть цель.

Использование:
    python3 epb_sroki.py EPB-NASHI-MASHINY.csv
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpb_po_inn as M  # noqa: E402

csv.field_size_limit(10 ** 7)
PUT = sys.argv[1] if len(sys.argv) > 1 else 'EPB-NASHI-MASHINY.csv'
KESH = PUT.replace('.csv', '-sroki.json')

rows = list(csv.DictReader(open(PUT, encoding='utf-8-sig'), delimiter=';'))
celi = [r for r in rows if r.get('centrobezhnoe') or r.get('nashe_oborudovanie')]
# Кеш по ссылке: один и тот же номер заключения встречается по нескольким ключевым словам,
# и дважды дёргать его карточку незачем.
kesh = json.load(open(KESH, encoding='utf-8')) if os.path.exists(KESH) else {}
nado = [r for r in celi if r['ssylka'] not in kesh]
print(f'строк всего {len(rows)}, наших машин {len(celi)}, карточек к запросу {len(nado)} '
      f'(в кеше {len(kesh)})', file=sys.stderr)

nov = [r for r in nado if r['ssylka'] not in kesh]
uniq = {r['ssylka']: r for r in nov}
zad = list(uniq.values())
M.dobrat_sroki(zad, potokov=8, tolko_nashe=False)
for r in zad:
    kesh[r['ssylka']] = {'deystvuet_do': r.get('deystvuet_do') or '',
                         'status': r.get('status') or ''}
json.dump(kesh, open(KESH, 'w', encoding='utf-8'), ensure_ascii=False)

kol = list(rows[0].keys())
for k in ('deystvuet_do', 'status'):
    if k not in kol:
        kol.append(k)
dat = deystv = istyok = 0
for r in rows:
    k = kesh.get(r['ssylka'])
    if not k:
        continue
    r['deystvuet_do'] = k['deystvuet_do']
    r['status'] = k['status']
    if k['deystvuet_do'][:2].isdigit():
        dat += 1
    if 'ист' in (k['status'] or ''):
        istyok += 1
    elif k['status']:
        deystv += 1
with open(PUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
centro_ist = [r for r in rows if r.get('centrobezhnoe') and 'ист' in (r.get('status') or '')]
print(f'дат получено {dat} | действует {deystv} | ИСТЁК СРОК {istyok} | '
      f'из них центробежных с истёкшей ЭПБ: {len(centro_ist)} '
      f'у {len({r["inn"] for r in centro_ist})} предприятий', file=sys.stderr)
