# -*- coding: utf-8 -*-
"""Сбор с Портала поставщиков Москвы рабочей формой запроса.

ФОРМА СНЯТА 1-Й СЕССИЕЙ, И ЭТО СНЯЛО МОЙ ТУПИК. Я перебирала обёртки вокруг `filter.nameLike`
и получала 500 на каждой, а неизвестные поля портал молча игнорировал — счётчик оставался
равен пустому запросу. Причина оказалась в ТИПЕ поля, а не в обёртке:

    "filter": {"nameLike": {"contains": true, "value": "компрессор"}}

`nameLike` — объект, а не строка. Проверка эталоном: пустой запрос 4 082 973, со словом
«компрессор» 3 056. Хост тоже другой: API отвечает на `old.zakupki.mos.ru`, а на основном
любой `/api/...` отдаёт оболочку SPA с кодом 200 — то есть «успешный» ответ, в котором нет
данных. Метод GET; POST даёт 405.

ЗАЧЕМ ЭТОТ КАНАЛ. В собранных 30 июля 5 681 строке 2 243 ИНН заказчиков, из них 2 228 нет в
списке предприятий реестра ЭПБ. Это самый большой единичный прирост охвата из всех открытых
каналов.

ДВА КОНТРОЛЯ В КАЖДОМ ПРОГОНЕ, иначе числам верить нельзя:
  * ЭТАЛОН ПУСТОГО ЗАПРОСА печатается первым. Если счётчик слова равен ему, фильтр не
    применился — и «нашлось 4 миллиона» читается как удача, хотя это отказ;
  * ЗАВЕДОМАЯ БЕССМЫСЛИЦА («йцукенгшщз») должна дать ноль. Ноль на ней — признак, что портал
    вообще фильтрует, а не отдаёт всем одно и то же.

Использование:
    python3 mos_sbor.py --slova компрессор,воздуходувка --out MOS.csv
    python3 mos_sbor.py --marki SLOVAR-MODELEY-1s-NASHI-DLYA-PLOSHCHADOK.txt --out MOS-MARKI.csv
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request

BAZA = 'https://old.zakupki.mos.ru/api/Cssp/Purchase/Query'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def zapros(slovo, skip=0, take=50, tajm=90, popytok=3):
    dto = {'filter': {'nameLike': {'contains': True, 'value': slovo}},
           'order': [{'field': 'relevance', 'desc': True}],
           'withCount': True, 'take': take, 'skip': skip}
    u = BAZA + '?queryDto=' + urllib.parse.quote(json.dumps(dto, ensure_ascii=False))
    for p in range(popytok):
        try:
            req = urllib.request.Request(u, headers={'User-Agent': UA,
                                                     'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=tajm) as r:
                telo = r.read().decode('utf-8', 'replace')
            if telo.lstrip()[:1] not in '{[':
                return None, [], 'оболочка SPA — ответ не от API'
            d = json.loads(telo)
            return d.get('count'), (d.get('items') or []), ''
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return None, [], f'{type(e).__name__}: {str(e)[:70]}'
            time.sleep(3 * (p + 1))
    return None, [], 'не дошло'


def kontrol():
    """Эталон пустого и бессмыслица. Возвращает (эталон, ноль_на_бессмыслице)."""
    etalon, _, e1 = zapros('', take=1)
    bessm, items, e2 = zapros('йцукенгшщзхъфывапр', take=1)
    print(f'КОНТРОЛЬ: пустой запрос {etalon} (ошибка: {e1 or "нет"}), '
          f'бессмыслица {bessm} (ошибка: {e2 or "нет"})', file=sys.stderr)
    if etalon is None:
        sys.exit('эталон не получен — канал закрыт, сбор бессмыслен')
    if bessm not in (0, None) and bessm == etalon:
        sys.exit('бессмыслица даёт столько же, сколько пустой запрос — фильтр не работает')
    return etalon, bessm


POLYA = ['nomer', 'predmet', 'zakon', 'zakazchik', 'zakazchik_inn', 'zakazchikov',
         'organizator', 'organizator_inn', 'cena', 'data_nachala', 'data_okonchaniya',
         'status', 'region', 'ssylka', 'vneshnyaya_ssylka', 'slovo', 'vsego_po_slovu']


def stroka(it, slovo, vsego):
    """Разбор элемента ПО НАСТОЯЩИМ именам полей, снятым с живого ответа.

    Первый прогон брал `customer.inn` и `customerInn` по памяти о том, как такие ответы
    обычно устроены: 1 768 строк записались, счётчики сошлись, контроль прошёл — и ноль ИНН
    у всех. Неверное имя поля не даёт ни ошибки, ни предупреждения. На самом деле заказчик
    лежит списком `customers[]`, а рядом есть `purchaseCreator` — это разные роли, и обе
    сохраняются: заказчиков у одной закупки бывает несколько.
    """
    ident = str(it.get('id') or '')            # «Need5756459» — вид и номер слитно
    m = re.match(r'([A-Za-z]+)(\d+)', ident)
    vid, nom = (m.group(1).lower(), m.group(2)) if m else ('', ident)
    zak = [c for c in (it.get('customers') or []) if isinstance(c, dict)]
    org = it.get('purchaseCreator') if isinstance(it.get('purchaseCreator'), dict) else {}
    return {'nomer': nom, 'predmet': (it.get('name') or '')[:400],
            'zakon': it.get('federalLawName') or '',
            # `or ''` до среза, а не после: у элемента поле name бывает null, и срез по
            # None валит весь прогон на середине выгрузки.
            'zakazchik': ((zak[0].get('name') or '') if zak else '')[:200],
            'zakazchik_inn': ((zak[0].get('inn') or '') if zak else ''),
            'zakazchikov': len(zak),
            'organizator': (org.get('name') or '')[:200],  # org уже гарантированный dict
            'organizator_inn': org.get('inn') or '',
            'cena': it.get('startPrice') or '',
            'data_nachala': (it.get('beginDate') or '')[:19],
            'data_okonchaniya': (it.get('endDate') or '')[:19],
            'status': str(it.get('stateName') or ''),
            'region': (it.get('regionName') or ''),
            'ssylka': f'https://zakupki.mos.ru/{vid}/{nom}' if nom else '',
            'vneshnyaya_ssylka': it.get('externalUrl') or '',
            'slovo': slovo, 'vsego_po_slovu': vsego}


def sobrat(slova, out_path, stranic=6, take=50, pauza=1.0):
    etalon, _ = kontrol()
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=POLYA, delimiter=';', extrasaction='ignore')
    w.writeheader()
    vsego_strok, nulevyh, sboev = 0, 0, 0
    vidennye = set()
    for k, slovo in enumerate(slova, 1):
        c, items, err = zapros(slovo, skip=0, take=take)
        if err:
            sboev += 1
            print(f'[{k}/{len(slova)}] {slovo[:30]:<30} СБОЙ: {err}', file=sys.stderr)
            continue
        if c == etalon:
            # Молчаливое игнорирование фильтра — не находка, а отказ. Печатаем и идём дальше.
            print(f'[{k}/{len(slova)}] {slovo[:30]:<30} ФИЛЬТР НЕ ПРИМЕНЁН (счётчик равен '
                  f'пустому запросу) — строки не берём', file=sys.stderr)
            sboev += 1
            continue
        vzyato = 0
        for st in range(stranic):
            if st:
                c2, items, err = zapros(slovo, skip=st * take, take=take)
                if err or not items:
                    break
            for it in items:
                r = stroka(it, slovo, c)
                klyuch = (r['nomer'], r['zakazchik_inn'])
                if klyuch in vidennye:
                    continue
                vidennye.add(klyuch)
                w.writerow(r)
                vzyato += 1
            if (st + 1) * take >= (c or 0):
                break
            time.sleep(pauza)
        f.flush()
        vsego_strok += vzyato
        if not vzyato:
            nulevyh += 1
        print(f'[{k}/{len(slova)}] {slovo[:30]:<30} счётчик {c:>7}, взято {vzyato:>4}, '
              f'всего {vsego_strok}', file=sys.stderr)
        time.sleep(pauza)
    f.close()
    inn = len({r[1] for r in vidennye if r[1]})
    print(f'итого {vsego_strok} строк, разных ИНН заказчиков {inn} | слов без результата '
          f'{nulevyh} | СБОЕВ (ноль недостоверен) {sboev} → {out_path}', file=sys.stderr)


def main():
    def arg(imya, po=None):
        return sys.argv[sys.argv.index(imya) + 1] if imya in sys.argv else po
    out = arg('--out', 'MOS-SBOR.csv')
    if '--marki' in sys.argv:
        slova = [x.strip() for x in open(arg('--marki'), encoding='utf-8-sig')
                 if x.strip() and not x.startswith('#')]
    else:
        slova = [x.strip() for x in (arg('--slova') or 'компрессор').split(',') if x.strip()]
    sobrat(slova, out, stranic=int(arg('--stranic', 6)), take=int(arg('--take', 50)))


if __name__ == '__main__':
    main()
