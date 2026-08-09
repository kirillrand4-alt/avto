# -*- coding: utf-8 -*-
"""Свод фактов: к разбору регуляркой добавляются марка от провайдера и СРОК со страницы.

Источники не заменяют друг друга, а дополняются — по общему решению (`istochniki`
накопительно). Марка от провайдера ставится ТОЛЬКО туда, где регулярка не справилась,
и помечается, чтобы было видно, чем добыта.
"""
import csv, json, os, sys, collections

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
FAKTY = os.path.join(L, 'PARK-FAKTY-2S-EPB-POLNYE.csv')
PROV = os.path.join(L, 'PARK-MARKA-PROVAJDER-2S.jsonl')
SROK = os.path.join(L, 'PARK-SROK-EPB-2S.jsonl')
VYHOD = os.path.join(L, 'PARK-FAKTY-2S-SVOD.csv')
csv.field_size_limit(10 ** 7)


def main():
    rows = list(csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';'))
    # марка от провайдера — по ключу (инн, начало цитаты), как её писал сам прогон
    prov = {}
    if os.path.exists(PROV):
        for ln in open(PROV, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if z.get('marka'):
                prov[z['klyuch']] = z
    srok = {}
    if os.path.exists(SROK):
        for ln in open(SROK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if z.get('srok_do') or z.get('status'):
                srok[z['ssylka']] = z
    sch = collections.Counter()
    cols = list(rows[0].keys()) + ['chem_marka', 'status_sroka', 'citata_sroka', 'istochnikov']
    for x in rows:
        x['chem_marka'] = 'регулярка' if x['marka_model'] else ''
        x['istochnikov'] = 1
        k = x['inn'] + '|' + x['citata'][:60]
        if not x['marka_model'] and k in prov:
            x['marka_model'] = prov[k]['marka']
            x['chem_marka'] = 'провайдер по тексту заключения'
            x['istochnikov'] = 2
            sch['марка добавлена провайдером'] += 1
        s = srok.get(x['ssylka'])
        x['status_sroka'] = ''
        x['citata_sroka'] = ''
        if s:
            if s.get('srok_do'):
                x['srok_do'] = s['srok_do']
                sch['срок добавлен со страницы'] += 1
            x['status_sroka'] = s.get('status') or ''
            x['citata_sroka'] = (s.get('citata') or '')[:150]
            x['istochnikov'] = int(x['istochnikov']) + 1
        if x['marka_model']:
            sch['с маркой'] += 1
        if x['srok_do']:
            sch['со сроком'] += 1
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    print(f'строк {len(rows)}, предприятий {len({x["inn"] for x in rows})}', file=sys.stderr)
    for k, v in sch.most_common():
        print(f'  {v:>7}  {k}', file=sys.stderr)
    print(f'  {sum(1 for x in rows if not x["ssylka"].strip()):>7}  БЕЗ ССЫЛКИ', file=sys.stderr)
    print(f'  {sum(1 for x in rows if x.get("status_sroka") == "истёк"):>7}  срок ИСТЁК', file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


main()
