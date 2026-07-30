# -*- coding: utf-8 -*-
"""202 предприятия воздушного сегмента без единого контакта: обогащение по ИНН через DaData.

Зачем. `novye-dlya-obzvona.csv` — 202 предприятия, у которых есть марка машины и срок ЭПБ, но
ноль контактов; вторая сессия назвала это «самой большой дырой». Пункт 3 очереди передачи.

Что здесь можно, а что нельзя — честно. Инструмент первой сессии `sayty_dlya_celey.py` ищет
официальный сайт в поисковой выдаче через xmlriver, а ключей `XMLRIVER_KEY`/`XMLRIVER_USER` нет
ни в `runner-secrets.env`, ни в `rs.env`, ни в `sender-secrets.env` — то есть этот путь отсюда
закрыт, и это блокер к владельцу, а не к сессии. Карточка ЭПБ (`monitor-pb.ru`) телефонов
предприятия не несёт: проверено на живой странице, там ноль номеров и только почта самого
сайта.

Что остаётся и делается здесь: справочник ЕГРЮЛ через DaData — он открывается прямо из
песочницы, токен лежит в ключнице раннера. Даёт официальное название, адрес, статус в ЕГРЮЛ и
**руководителя с должностью**. Руководитель — не технарь, и выдавать его за технаря нельзя; он
нужен как подтверждённая точка входа и как проверка, что юрлицо живое.

Заслон: запрос идёт по ИНН (идентификатор), а не по названию. Сличение названий строками
подводило прошлые сессии трижды, а по ИНН двусмысленности нет.

Использование:
    python3 celi_202_dadata.py [--vhod ФАЙЛ] [--vyhod ФАЙЛ] [--threads 6]
"""
import csv
import json
import os
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party'
BAZA = os.path.dirname(os.path.abspath(__file__))


def token():
    t = os.environ.get('DADATA_TOKEN')
    if not t:
        sys.exit('нет DADATA_TOKEN в окружении')
    return t


def sprosit(inn, tok):
    body = json.dumps({'query': inn, 'count': 5}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': f'Token {tok}'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def main():
    vhod = sys.argv[sys.argv.index('--vhod') + 1] if '--vhod' in sys.argv \
        else '/home/user/work/novye-dlya-obzvona.csv'
    vyhod = sys.argv[sys.argv.index('--vyhod') + 1] if '--vyhod' in sys.argv \
        else os.path.join(BAZA, 'engineers-lens', 'centro', 'celi-202-dadata.csv')
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 6
    tok = token()
    rows = list(csv.DictReader(open(vhod, encoding='utf-8-sig'), delimiter=';'))
    print(f'предприятий на входе: {len(rows)}', file=sys.stderr)
    lock = threading.Lock()
    sch = {'nashli': 0, 'ruk': 0, 'live': 0, 'err': 0}

    def odno(r):
        inn = (r.get('inn') or '').strip()
        try:
            o = sprosit(inn, tok)
        except Exception as e:  # noqa: BLE001
            return r, None, f'{type(e).__name__}: {str(e)[:60]}'
        # Берём подсказку, у которой ИНН совпал ТОЧНО: справочник на запрос по ИНН может
        # вернуть и филиалы, и однофамильцев по другим полям.
        for s in o.get('suggestions') or []:
            d = s.get('data') or {}
            if (d.get('inn') or '') == inn:
                return r, (s, d), ''
        return r, None, 'точного совпадения по ИНН нет'

    kol = ['inn', 'predpriyatie', 'ofic_nazvanie', 'status', 'adres', 'rukovoditel',
           'dolzhnost_rukovoditelya', 'okved', 'marki_mashin', 'vozdushnyh_zaklyucheniy',
           'posledneye_zaklyuchenie', 'oshibka']
    itog = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for r, nash, err in pool.map(odno, rows):
            with lock:
                if err or not nash:
                    sch['err'] += 1
                    itog.append({**{k: '' for k in kol}, 'inn': r.get('inn', ''),
                                 'predpriyatie': r.get('predpriyatie', ''),
                                 'marki_mashin': r.get('marki_mashin', ''),
                                 'oshibka': err or 'не найдено'})
                    continue
                s, d = nash
                m = (d.get('management') or {})
                sch['nashli'] += 1
                if m.get('name'):
                    sch['ruk'] += 1
                if (d.get('state') or {}).get('status') == 'ACTIVE':
                    sch['live'] += 1
                itog.append({
                    'inn': d.get('inn') or '', 'predpriyatie': r.get('predpriyatie', ''),
                    'ofic_nazvanie': (d.get('name') or {}).get('short_with_opf') or '',
                    'status': (d.get('state') or {}).get('status') or '',
                    'adres': (d.get('address') or {}).get('value') or '',
                    'rukovoditel': m.get('name') or '',
                    'dolzhnost_rukovoditelya': m.get('post') or '',
                    'okved': d.get('okved') or '',
                    'marki_mashin': r.get('marki_mashin', ''),
                    'vozdushnyh_zaklyucheniy': r.get('vozdushnyh_zaklyucheniy', ''),
                    'posledneye_zaklyuchenie': r.get('posledneye_zaklyuchenie', ''),
                    'oshibka': ''})
    with open(vyhod, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    print(f'найдено в ЕГРЮЛ: {sch["nashli"]} из {len(rows)}, действующих {sch["live"]}, '
          f'с руководителем {sch["ruk"]}, не найдено/ошибок {sch["err"]} → {vyhod}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
