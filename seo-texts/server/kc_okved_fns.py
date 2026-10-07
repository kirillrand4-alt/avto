# -*- coding: utf-8 -*-
r"""База КЦ: основной ОКВЭД для юрлиц с доходом 2025 >= 3 млрд (ФНС revexp), которых нет в наших
базах (kc-pishch-probel.json, «нет»: 11 209 ИНН). Без этого в отбор не попадают крупные
мясокомбинаты/молочка/корма/напитки, которых никогда не было в базе обзвона.

Два потока с разных концов списка (по убыванию дохода), пока не встретятся:
  * DaData findById — сверху, не больше ЛИМИТ_DADATA запросов (бесплатно 10k/день, часть дня
    оставляем news-scan'у); 403/429 — поток DaData останавливается;
  * checko.ru (поиск по ИНН -> карточка) через прокси владельца — снизу; заодно сайт из карточки.
Выход (fsync, резюм по ИНН): C:\sender\server\kc-okved-fns.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
import cc_checko_proxy as CP  # noqa: E402
import enrich_contacts as EC  # noqa: E402

ВЫХОД = os.path.join(DIR, 'kc-okved-fns.jsonl')
ЛИМИТ_DADATA = 2000  # 2-й запуск 07.10: 6 500 уже израсходовано, ~1 500 оставляем news-scan
ПОТОКОВ_DADATA = 10
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    вход = json.load(io.open(os.path.join(DIR, 'kc-pishch-probel.json'), encoding='utf-8'))['нет']
    очередь = sorted(вход, key=lambda i: -вход[i])
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') in ('ok', 'не найден'):
                    сделано.add(з['inn'])
            except ValueError:
                pass
    очередь = [i for i in очередь if i not in сделано]
    гр = {'верх': 0, 'низ': len(очередь)}
    гл = threading.Lock()

    def взять(сверху):
        with гл:
            if гр['верх'] >= гр['низ']:
                return None
            if сверху:
                гр['верх'] += 1
                return очередь[гр['верх'] - 1]
            гр['низ'] -= 1
            return очередь[гр['низ']]

    tok = EC._read_secret('DADATA_TOKEN')
    прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    сч = {'dadata': 0, 'checko': 0, 'ошибки': 0}

    def поток_dadata():
        while сч['dadata'] < ЛИМИТ_DADATA and 'стоп_dadata' not in сч:
            i = взять(True)
            if i is None:
                return
            з = {'inn': i, 'доход': вход[i], 'источник': 'dadata'}
            try:
                req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                                             data=json.dumps({'query': i}).encode(), method='POST', headers={
                                                 'Content-Type': 'application/json', 'Accept': 'application/json',
                                                 'Authorization': 'Token ' + tok})
                с = json.loads(прямой.open(req, timeout=40).read()).get('suggestions') or []
                with гл:
                    сч['dadata'] += 1
                if с:
                    d = с[0]['data']
                    а = (d.get('address') or {}).get('data') or {}
                    з.update({'итог': 'ok', 'оквэд': d.get('okved') or '', 'название': (d.get('name') or {}).get('short_with_opf') or с[0].get('value'),
                              'регион': а.get('region_with_type') or '', 'статус': (d.get('state') or {}).get('status') or '',
                              'огрн': d.get('ogrn') or ''})
                else:
                    з['итог'] = 'не найден'
            except urllib.error.HTTPError as e:
                з.update({'итог': 'ошибка', 'ошибка': 'HTTP %s' % e.code})
                записать(з)  # ИНН с ошибкой подберёт повторный запуск (резюм)
                if e.code in (403, 429):
                    сч['стоп_dadata'] = 'HTTP %s после %d запросов' % (e.code, сч['dadata'])
                    return
                continue
            except Exception as e:  # noqa: BLE001
                з.update({'итог': 'ошибка', 'ошибка': repr(e)[:80]})
            записать(з)
            time.sleep(0.2)

    def поток_checko(п):
        while True:
            i = взять(False)
            if i is None:
                return
            з = {'inn': i, 'доход': вход[i], 'источник': 'checko'}
            код, html = п.get('https://checko.ru/search?query=%s' % i)
            if код != 200:
                з.update({'итог': 'ошибка', 'ошибка': str(код)})
                сч['ошибки'] += 1
                записать(з)
                continue
            т = CP.текст(html)
            if 'По вашему запросу ничего не найдено' in т or 'ничего не найдено' in т[:3000]:
                з['итог'] = 'не найден'
                записать(з)
                continue
            ок = CP.окведы(т)
            заг = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
            сайт = re.search(r'Сайт\s+((?:https?://)?(?:www\.)?[a-zа-я0-9\-]+(?:\.[a-zа-я0-9\-]+)+)', т, re.I)
            з.update({'итог': 'ok' if ок else 'нет оквэд', 'оквэд': ок[0] if ок else '', 'оквэд_все': ок[:40],
                      'название': re.sub(r'\s+', ' ', заг.group(1)).strip()[:150] if заг else '',
                      'статус': 'ликвидирована' if re.search(r'ликвидирован|прекратил[ао]? деятельность', т[:6000], re.I) else '',
                      'сайт': сайт.group(1) if сайт else ''})
            сч['checko'] += 1
            записать(з)

    прокси = [CP.Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
    прокси = [п for п in прокси if п.get('https://checko.ru/')[0] == 200]
    print('очередь', len(очередь), 'прокси', len(прокси), flush=True)
    # DaData с сервера отвечает 10–20 с на запрос (замер 07.10) — 10 потоков
    нити = [threading.Thread(target=поток_dadata) for _ in range(ПОТОКОВ_DADATA)] + [threading.Thread(target=поток_checko, args=(п,)) for п in прокси]
    for н in нити:
        н.start()
    t0 = time.time()
    while any(н.is_alive() for н in нити):
        time.sleep(60)
        print('%d мин: dadata %d, checko %d, ошибок checko %d, осталось %d %s' % (
            (time.time() - t0) / 60, сч['dadata'], сч['checko'], сч['ошибки'], гр['низ'] - гр['верх'],
            сч.get('стоп_dadata', '')), flush=True)
    shutil.copyfile(ВЫХОД, r'C:\seostat\drop\drop-storage\kc-okved-fns.jsonl')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
