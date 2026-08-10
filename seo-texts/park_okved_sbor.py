# -*- coding: utf-8 -*-
"""ВСЕ коды ОКВЭД со страницы /activity чеко. ОГРН свой, dadata не нужна.

СЛОВО ВЛАДЕЛЬЦА: «все коды оквед нужны». Основной код без остальных не отвечает на вопрос,
чем предприятие занимается: у завода с основным «производство прочих машин» вторичными
стоят и ремонт, и монтаж, и торговля — по ним и решается, наш это покупатель или конкурент.

ОТКУДА АДРЕС И ПРАВИЛО. Из готовой операции `enrich_contacts.py op=checko_okveds`, а не
придуманы: страница `checko.ru/company/<ОГРН>/activity`, таблица «Виды деятельности».
Там же сказано, что dadata на нашем тарифе дополнительные ОКВЭД НЕ отдаёт вовсе.

ПОЧЕМУ НЕ ЗАПУСКАЮ ГОТОВУЮ ОПЕРАЦИЮ, а беру из неё только правила. Она берёт ОГРН
исключительно из dadata, а dadata с боевого сервера отвечает
`urlopen error Tunnel connection failed: 407 Proxy` — проверено на шести ИНН, у всех шести
пустой ОГРН и пустые коды. Ключа для передачи ОГРН в аргументах у неё нет (грепал).
А ОГРН у меня УЖЕ ЕСТЬ: он стоит в адресе карточки, собранной прошлым заходом
(`https://checko.ru/company/pervouralskgaz-1026601503510/contacts`).

КАПКАН, НАЗВАННЫЙ В ГОТОВОМ КОДЕ И ОПЛАЧЕННЫЙ ЧУЖОЙ СМЕНОЙ: регулярка по ВСЕЙ странице
тащит мусор из шапки чеко («12.5», «22.5» — лезли первыми у всех 473 компаний), из-за чего
основной ОКВЭД оказывался мусором и гейт конкурента не срабатывал ни разу. Поэтому текст
РЕЖЕТСЯ по заголовку раздела видов деятельности, и только потом ищутся коды.

Запуск на VPS: python park_okved_sbor.py <бюджет_сек>
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
BYUDZHET = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
VHOD, POTOK = 'PARK-CHECKO-2S.jsonl', 'PARK-OKVED-2S.jsonl'
NACHALO = time.time()
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
OGRN = re.compile(r'/company/(?:[^/]*?-)?(\d{13,15})')
RAZDEL = re.compile(r'(Виды\s+деятельности|Основной\s+вид\s+деятельности|ОКВЭД)')
KOD = re.compile(r'\b\d{2}\.\d{1,2}(?:\.\d{1,2})?\b')
IMYA_KODA = re.compile(r'\b(\d{2}\.\d{1,2}(?:\.\d{1,2})?)\s*[—–\-:.]?\s*([А-ЯЁа-яё][^|]{3,110}?)'
                       r'(?=\s+\d{2}\.\d{1,2}\b|\s*$)')


def drop_get(i):
    return urllib.request.urlopen(urllib.request.Request(
        f'{DROP}/{i}', headers={'X-Drop-Token': TOKEN}), timeout=180).read()


def drop_put(i, telo):
    return urllib.request.urlopen(urllib.request.Request(
        f'{DROP}/{i}', data=telo, method='PUT',
        headers={'X-Drop-Token': TOKEN}), timeout=300).read()


zamok = threading.Lock()
sch = {'целей': 0, 'страниц': 0, 'с кодами': 0, 'кодов всего': 0, 'без ОГРН': 0, 'сбоев': 0}


def main():
    celi = []
    for l in drop_get(VHOD).decode('utf-8', 'replace').splitlines():
        try:
            d = json.loads(l)
        except Exception:  # noqa: BLE001
            continue
        m = OGRN.search(d.get('kartochka') or '')
        if m:
            celi.append((d['inn'], m.group(1), d.get('predpriyatie', '')))
        else:
            sch['без ОГРН'] += 1
    gotovo = set()
    try:
        for l in drop_get(POTOK).decode('utf-8', 'replace').splitlines():
            try:
                gotovo.add(json.loads(l)['inn'])
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    celi = [c for c in celi if c[0] not in gotovo]
    px = [(s if s.strip().startswith('socks5') else 'socks5://' + s.strip())
          for s in drop_get('dolphin-proxies.txt').decode('utf-8', 'replace').splitlines()
          if s.strip() and '@' in s]
    sch['целей'] = len(celi)
    print(json.dumps({'к обходу': len(celi), 'уже сделано': len(gotovo),
                      'без ОГРН': sch['без ОГРН'], 'прокси': len(px)}, ensure_ascii=False),
          flush=True)
    f = io.open(os.path.basename(POTOK), 'w', encoding='utf-8')

    def odna(t):
        idx, (inn, ogrn, imya) = t
        if time.time() - NACHALO > BYUDZHET:
            return
        p = px[idx % len(px)] if px else None
        u = f'https://checko.ru/company/{ogrn}/activity'
        try:
            r = requests.get(u, headers=UA, timeout=40,
                             proxies={'http': p, 'https': p} if p else None)
            if r.status_code != 200:
                with zamok:
                    sch['сбоев'] += 1
                return
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.text))
        except Exception:  # noqa: BLE001
            with zamok:
                sch['сбоев'] += 1
            return
        m = RAZDEL.search(txt)
        kusok = txt[m.start():] if m else ''
        kody, vidal = [], set()
        for k in KOD.findall(kusok):
            if k not in vidal:
                vidal.add(k)
                kody.append(k)
        imena = {}
        for k, n in IMYA_KODA.findall(kusok):
            imena.setdefault(k, ' '.join(n.split())[:110].strip(' .,;'))
        with zamok:
            sch['страниц'] += 1
            if kody:
                sch['с кодами'] += 1
                sch['кодов всего'] += len(kody)
            f.write(json.dumps({'inn': inn, 'ogrn': ogrn, 'predpriyatie': imya,
                                'okved_kody': kody, 'okvedov': len(kody),
                                'okved_s_imenami': [k + ' ' + imena.get(k, '') for k in kody],
                                'ssylka': u,
                                'istochnik': 'checko.ru, раздел «Виды деятельности»'},
                               ensure_ascii=False) + '\n')
            f.flush()
            if sch['страниц'] % 50 == 0:
                print(json.dumps(sch, ensure_ascii=False), flush=True)

    with ThreadPoolExecutor(max_workers=24) as pool:
        list(pool.map(odna, list(enumerate(celi))))
    f.close()
    staroe = b''
    try:
        staroe = drop_get(POTOK)
    except Exception:  # noqa: BLE001
        pass
    drop_put(POTOK, staroe + io.open(os.path.basename(POTOK), 'rb').read())
    print(json.dumps(sch, ensure_ascii=False), flush=True)


main()
