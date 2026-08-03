# -*- coding: utf-8 -*-
"""Кто на самом деле купил: раздача закупок со страницы холдинга их настоящим юрлицам.

Зачем. Обход по страницам компаний (`tp_po_ocheredi.py`) даёт не только закупки самой
компании. Страница управляющей компании показывает закупки ВСЕГО холдинга, страница головного
предприятия — закупки филиалов. Замер 03.08 на 455 пройденных предприятиях: 4 135 строк свои,
2 105 филиальные, 602 принадлежат чужим юрлицам — и почти все 602 висят на одной странице,
«РУСАЛ Менеджмент (непрофильные активы)».

Приписать их РУСАЛ Менеджменту — соврать продавцу дважды. Во-первых, машину эксплуатирует
завод (Боксит Тимана, КраМЗ, СУБР, Уральская фольга), и разговаривать надо с его главным
энергетиком. Во-вторых, это отдельные предприятия, часть из них в нашей очереди отсутствует
вовсе — то есть это не мусор, а потерянные адресаты.

Как определяется настоящий владелец. Не по названию: на именах мы обжигались трижды
(«комбинат» слипался с «комбинатом хлебопродуктов»). Страница компании площадки печатает в
шапке «ИНН/КПП 1117000011/111701001» — это идентификатор из ЕГРЮЛ. Спрашиваем 63 страницы
(по числу разных company_id в не-своих строках), получаем точный ИНН каждой.

Что делается с результатом:
  * строка получает колонку `inn_vladelca` — ИНН того, кто закупал;
  * если этот ИНН уже есть в нашей очереди — закупка присоединяется к нему;
  * если нет — предприятие попадает в `tp-novye-predpriyatiya.csv` как КАНДИДАТ. Кандидат
    не лид: он обязан пройти те же заслоны `tip_mashiny.py`, что и все остальные. Файл — вход
    в общий конвейер, а не обход его.

Использование:
    python3 tp_vladelcy_zakupok.py              # разрешить ИНН и разложить закупки
    python3 tp_vladelcy_zakupok.py --tolko-karta   # только карта company_id → ИНН
"""
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tenderpro_harvest as T  # noqa: E402

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
OUT = os.path.join(L, 'centro', 'tenderpro')
# Два файла обхода по компаниям: словарный и БЕЗ СЛОВАРЯ. Раскладка владельцев одинаково
# нужна обоим, поэтому читаются оба и складываются с дедупом по (tender_id, ИНН страницы).
# Отдельные файлы у них потому, что прогоны надо было сравнить числом; но владелец у закупки
# один и тот же, и карта company_id → ИНН общая.
ISHODNIKI = [os.path.join(OUT, 'tp-spisok-po-kompaniyam.csv'),
             os.path.join(OUT, 'tp-spisok-po-kompaniyam-vsyo.csv')]
KARTA = os.path.join(OUT, 'tp-cid-inn.csv')
RAZLOZHENO = os.path.join(OUT, 'tp-zakupki-po-vladelcam.csv')
NOVYE = os.path.join(OUT, 'tp-novye-predpriyatiya.csv')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def pisat(put, rows, cols):
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def sobrat_kartu(cids, karta):
    """Спросить площадку про те company_id, которых ещё нет в карте. Карта копится на диске:
    страниц немного, но повторный опрос — это лишняя нагрузка на чужой сервер без нужды."""
    nado = [c for c in cids if c and c not in karta]
    if not nado:
        return karta
    print(f'спрашиваю площадку про {len(nado)} компаний', file=sys.stderr)

    def odna(cid):
        try:
            return cid, T.inn_po_company_id(cid)
        except Exception as e:  # noqa: BLE001
            return cid, ('', '', f'сбой: {type(e).__name__}')

    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, (cid, r) in enumerate(pool.map(odna, nado), 1):
            karta[cid] = {'company_id': cid,
                          'inn': (r or ('', '', ''))[0],
                          'kpp': (r or ('', '', ''))[1],
                          'nazvanie_na_ploshchadke': (r or ('', '', ''))[2][:120]}
            if i % 20 == 0:
                print(f'  {i}/{len(nado)}', file=sys.stderr, flush=True)
            time.sleep(0.2)
    pisat(KARTA, list(karta.values()),
          ['company_id', 'inn', 'kpp', 'nazvanie_na_ploshchadke'])
    return karta


def main():
    rows, vidano = [], set()
    for put in ISHODNIKI:
        for r in chitat(put):
            k = ((r.get('tender_id') or '').strip(), (r.get('inn') or '').strip())
            if k[0] and k in vidano:
                continue
            vidano.add(k)
            r['otkuda_obhod'] = ('словарный' if put.endswith('po-kompaniyam.csv')
                                 else 'страница компании целиком')
            rows.append(r)
    if len(rows) < 1000:
        sys.exit(f'на входе {len(rows)} строк — обход по компаниям ещё не набрал объём, '
                 'запускать раскладку рано')
    print(f'на входе {len(rows)} строк из {len([p for p in ISHODNIKI if os.path.exists(p)])} '
          f'файлов обхода', file=sys.stderr)
    karta = {r['company_id']: r for r in chitat(KARTA)}
    karta = sobrat_kartu(sorted({r['company_id'] for r in rows}), karta)
    if '--tolko-karta' in sys.argv:
        print(f'→ {KARTA}: {len(karta)} записей, ИНН известен у '
              f'{sum(1 for v in karta.values() if v["inn"])}', file=sys.stderr)
        return

    ochered = {r['inn'] for r in chitat(OCHERED)}
    schet = {'своих': 0, 'разложено филиалам': 0, 'разложено чужим': 0,
             'ИНН не отдался': 0, 'попало в очередь': 0, 'новых предприятий': 0}
    novye = {}
    for r in rows:
        k = karta.get(r['company_id']) or {}
        vlad = (k.get('inn') or '').strip()
        r['inn_vladelca'] = vlad or r['inn']
        r['vladelec_nazvanie'] = k.get('nazvanie_na_ploshchadke') or r['company']
        if r['chya_zakupka'].startswith('её'):
            schet['своих'] += 1
            continue
        if not vlad:
            schet['ИНН не отдался'] += 1
            r['inn_vladelca'] = ''          # пусто честнее, чем чужой ИНН
            continue
        schet['разложено филиалам' if r['chya_zakupka'].startswith('филиал')
              else 'разложено чужим'] += 1
        if vlad in ochered:
            schet['попало в очередь'] += 1
        elif vlad not in novye:
            novye[vlad] = {'inn': vlad, 'predpriyatie': r['vladelec_nazvanie'],
                           'otkuda': f'страница {r["predpriyatie"]} на Tender.pro',
                           'zakupok': 0, 'primer_predmeta': r['predmet'][:150]}
        if vlad in novye:
            novye[vlad]['zakupok'] += 1
    schet['новых предприятий'] = len(novye)

    pisat(RAZLOZHENO, rows, list(rows[0].keys()))
    pisat(NOVYE, sorted(novye.values(), key=lambda x: -x['zakupok']),
          ['inn', 'predpriyatie', 'otkuda', 'zakupok', 'primer_predmeta'])
    for k, v in schet.items():
        print(f'  {k}: {v}', file=sys.stderr)
    print(f'→ {RAZLOZHENO}\n→ {NOVYE}\n→ {KARTA}', file=sys.stderr)
    print('НОВЫЕ предприятия — кандидаты, а не лиды: их надо прогнать через tip_mashiny.py '
          'теми же заслонами, иначе в панель попадёт мусор', file=sys.stderr)


if __name__ == '__main__':
    main()
