# -*- coding: utf-8 -*-
"""Поиск сайта и контактов раннером по любому списку ИНН — с честным разделением «чей это сайт».

Зачем отдельно от `vodokanaly_obogatit.py`: тот же приём нужен не одному сегменту, а главной
очереди — 2 095 предприятий, где ДОКАЗАНА центробежная машина, и у 2 020 из них сайта нет.

Замер на 64 водоканалах, ради которого здесь всё построено именно так:

    найден сайт                                     60 из 64
    из них судья сказал «сайт НЕ этой компании»     29
    сайт найден И подтверждён (inn или provider)    16  → у всех 16 телефоны и почты
    ничего                                          19
    расход: 134 запроса xmlriver на 64 компании = 2,1 на компанию, около 5 копеек

То есть **«найден сайт» и «найден ЕЁ сайт» расходятся втрое**. Брать телефоны с непроверенного
сайта нельзя: у 28 компаний из 29 «чужих» телефоны были, и это телефоны другой организации.
Поэтому подтверждённые и чужие контакты пишутся в РАЗНЫЕ колонки, а не сливаются.

Использование:
    python3 sajty_po_ocheredi.py --spisok engineers-lens/OCHERED-centrobezhnye.csv \
        [--predel 400] [--pachka 8] [--parallel 3]
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'


def dovod(arg, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(arg) + 1]) if arg in sys.argv else po_umolchaniyu


def main():
    spisok = dovod('--spisok', os.path.join(BAZA, 'engineers-lens', 'OCHERED-centrobezhnye.csv'))
    predel = dovod('--predel', 400)
    pachka = dovod('--pachka', 8)
    parallel = dovod('--parallel', 3)
    metka = re.sub(r'\W+', '_', os.path.basename(spisok))[:40]
    put_res = os.path.join(RAB, f'sajty_{metka}.jsonl')

    rows = list(csv.DictReader(open(spisok, encoding='utf-8-sig'), delimiter=';'))
    # уже известный сайт трогать незачем: ищем только тем, у кого его нет
    rows = [r for r in rows if not (r.get('sayt') or r.get('site') or '').strip()]
    gotovo = set()
    if os.path.exists(put_res):
        for l in open(put_res, encoding='utf-8'):
            try:
                gotovo.add(json.loads(l).get('inn'))
            except json.JSONDecodeError:
                pass
    rows = [r for r in rows if r['inn'] not in gotovo][:predel]
    print(f'к поиску: {len(rows)} (уже пройдено {len(gotovo)}) из {spisok}', file=sys.stderr)
    if not rows:
        return
    pachki = [rows[i:i + pachka] for i in range(0, len(rows), pachka)]
    lock = threading.Lock()
    f = open(put_res, 'a', encoding='utf-8')
    sch = {'сайт подтверждён': 0, 'сайт чужой': 0, 'ничего': 0, 'телефоны': 0, 'почты': 0,
           'люди': 0, 'xmlriver': 0}

    def odna(gr):
        comp = [{'inn': x['inn'], 'ogrn': '',
                 'name': (x.get('predpriyatie') or x.get('name') or '')[:90],
                 'site': '', 'phones': (x.get('telefony_predpriyatiya') or '')[:120]} for x in gr]
        p = subprocess.run([sys.executable, KLIENT, 'enrich_contacts',
                            json.dumps({'companies': comp, 'site_crawl': True}, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=2400)
        m = re.search(r'\{.*\}', p.stdout, re.S)
        if not m:
            return gr, None, (p.stdout or p.stderr)[-160:]
        try:
            return gr, json.loads(m.group(0)), ''
        except json.JSONDecodeError as e:
            return gr, None, f'JSON не разобран: {str(e)[:60]}'

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for i, (gr, res, err) in enumerate(pool.map(odna, pachki), 1):
            with lock:
                if err:
                    print(f'  СБОЙ пачки {i}: {err[:120]}', file=sys.stderr, flush=True)
                    continue
                dd = res.get('data') or {}
                sch['xmlriver'] += ((dd.get('cost') or {}).get('xmlriver') or 0)
                po_inn = {}
                for x in dd.get('results') or []:
                    po_inn.setdefault(x.get('inn') or '', []).append(x)
                for x in gr:
                    rr = po_inn.get(x['inn']) or []
                    f.write(json.dumps({'inn': x['inn'],
                                        'predpriyatie': (x.get('predpriyatie') or '')[:70],
                                        'rezultaty': rr}, ensure_ascii=False) + '\n')
                    svoy = [y for y in rr if str(y.get('verified')) in ('inn', 'provider')]
                    chuzh = [y for y in rr if str(y.get('verified')) == 'mismatch']
                    if svoy:
                        sch['сайт подтверждён'] += 1
                        if any(y.get('phones') for y in svoy):
                            sch['телефоны'] += 1
                        if any(y.get('emails') for y in svoy):
                            sch['почты'] += 1
                        sch['люди'] += sum(1 for y in svoy for e in (y.get('emails') or [])
                                           if isinstance(e, dict) and (e.get('person') or '').strip())
                    elif chuzh:
                        sch['сайт чужой'] += 1
                    else:
                        sch['ничего'] += 1
                f.flush()
                print(f'  пачек {i}/{len(pachki)}: ' + ', '.join(f'{k} {v}' for k, v in sch.items()),
                      file=sys.stderr, flush=True)
    f.close()
    print(f'готово → {put_res}', file=sys.stderr)


if __name__ == '__main__':
    main()
