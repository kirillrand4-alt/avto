# -*- coding: utf-8 -*-
r"""ОКВЭД (основной + все) и выручка по ИНН базы CC (владелец 07.10: «выручку пропиши», «оквэд
основные и доп тоже»).

ОКВЭД — штатной операцией enrich_contacts op=checko_okveds (основной из DaData, полный список со
страницы checko.ru/company/<ОГРН>/activity; она же пишет в enrich.db). Выручка — со страницы
checko.ru/company/<ОГРН> (обычный HTTP, как activity). Вход: C:\seostat\drop\drop-storage\
cc-inn-dlya-checko.txt. Выход (fsync, резюм по ИНН): C:\sender\server\cc-checko.jsonl.
"""
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ВХОД = r'C:\seostat\drop\drop-storage\cc-inn-dlya-checko.txt'
ВЫХОД = os.path.join(DIR, 'cc-checko.jsonl')
_лок = threading.Lock()
ЕДИНИЦЫ = {'трлн': 1e12, 'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def выручка(ogrn):
    # checko режет частые запросы (429): один поток, пауза, повтор после паузы
    for попытка in range(4):
        time.sleep(2.5)
        ст, html, _ = MN.скачать('https://checko.ru/company/%s' % ogrn)
        if '429' not in ст:
            break
        time.sleep(30 * (попытка + 1))
    if ст != 'ok':
        return {'выручка_страница': ст}
    т = re.sub(r'\s+', ' ', MP.в_текст(html))
    out = {'выручка_страница': 'ok'}
    for м in re.finditer(r'Выручка', т):
        кус = т[м.start():м.start() + 160]
        ч = re.search(r'(\d[\d \u00a0]*(?:[.,]\d+)?)\s*(трлн|млрд|млн|тыс)?\.?\s*(?:руб|₽)', кус)
        if ч:
            число = float(ч.group(1).replace(' ', '').replace('\u00a0', '').replace(',', '.'))
            out['выручка_руб'] = int(число * ЕДИНИЦЫ.get(ч.group(2) or '', 1))
            г = re.search(r'(20\d\d)\s*г', т[max(0, м.start() - 120):м.start() + 200])
            out['выручка_год'] = г.group(1) if г else ''
            out['выручка_фрагмент'] = кус[:140]
            break
    return out


def пачка(инн):
    p = subprocess.run([sys.executable, os.path.join(DIR, 'enrich_contacts.py')],
                       input=json.dumps({'op': 'checko_okveds', 'inns': инн}, ensure_ascii=False),
                       capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=DIR, timeout=1800)
    i = p.stdout.find('{')
    try:
        res = json.loads(p.stdout[i:])['results']
    except Exception:  # noqa: BLE001
        for x in инн:
            записать({'inn': x, 'ошибка': (p.stderr or p.stdout)[-200:]})
        return
    for r in res:
        if r.get('ogrn'):
            r.update(выручка(r['ogrn']))
        записать(r)


def main():
    инн = [s.strip() for s in io.open(ВХОД, encoding='utf-8') if s.strip()]
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('okveds_all') or з.get('выручка_руб'):
                    сделано.add(з['inn'])
            except ValueError:
                pass
    очередь = [i for i in инн if i not in сделано]
    print('ИНН', len(инн), 'в очереди', len(очередь), flush=True)
    пачки = [очередь[i:i + 10] for i in range(0, len(очередь), 10)]
    t0 = time.time()
    with ThreadPoolExecutor(1) as ex:
        for k, _ in enumerate(ex.map(пачка, пачки)):
            print('пачек %d/%d за %d мин' % (k + 1, len(пачки), (time.time() - t0) / 60), flush=True)
    print('готово', flush=True)


if __name__ == '__main__':
    main()
