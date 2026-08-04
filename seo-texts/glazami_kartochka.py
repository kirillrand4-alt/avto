# -*- coding: utf-8 -*-
"""Показать снятую карточку панели так, чтобы её можно было ПРОЧИТАТЬ.

Счётчик дефектов (`defekty_paneli_po_kartochkam.py`) отвечает «сколько и каких», и этого мало:
владелец просит смотреть глазами, а глазами видно то, чего в списке классов нет. Этот модуль
ничего не считает — он раскладывает карточку в текст: шапка, суд, состояние, контакты, люди,
факты с цитатами. Дальше читаю я.

Использование:
    python3 glazami_kartochka.py снимок.json [ИНН]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import razbor_kartochki_paneli as R


def pokazat(inn, k):
    print('=' * 100)
    print(f"{inn}  {k['nazvanie']}")
    print(f"  регион {k.get('регион') or '—'} | приоритет {k.get('приоритет')} | "
          f"фактов {k.get('фактов')} | {k['sud']} | состояние: {k.get('состояние')}")
    print(f"  адрес: {k['adres'][:96]}")
    r = k['rekvizity']
    print(f"  ОКВЭД: {(r.get('Основной ОКВЭД') or '—')[:96]}")
    print(f"  статус ЕГРЮЛ: {r.get('Статус ЕГРЮЛ')} | директор: {(r.get('Директор') or '—')[:60]}")
    print(f"  выручка: {r.get('Выручка') or '—'} | сотрудники: {r.get('Сотрудники') or '—'}")
    print(f"  почему звонить: {k['pochemu_zvonit']}")
    print(f"  убрано продавцом: {k['ubrano'] or '0'} | «мусора нет»: {k['musor_fraza']}")
    if k['lyudi']:
        print(f"  ЛЮДИ ({len(k['lyudi'])}):")
        for l in k['lyudi']:
            print(f"    {'тех' if l['tehnicheskiy'] else '   '} {l['chelovek'][:38]:38} | "
                  f"{l['dolzhnost'][:34]:34} | {l['istochnik'][:34]}")
    else:
        print('  ЛЮДЕЙ НЕТ')
    if k['kontakty']:
        print(f"  КОНТАКТЫ ({len(k['kontakty'])}): "
              + ', '.join(c['znachenie'] for c in k['kontakty'][:10]))
        print('    источники: ' + ' | '.join(sorted({c['istochnik'][:40] for c in k['kontakty']})))
    print(f"  ФАКТЫ ({len(k['fakty'])} разобрано):")
    for f in k['fakty']:
        print(f"    [{f.get('статус','')}] тип: {f.get('Тип оборудования','—')} | "
              f"среда: {f.get('Рабочая среда','—')} | марка: {f.get('Модель / марка','—')}")
        print(f"       цитата: {(f.get('Цитата') or '')[:150]}")
        print(f"       чем доказано: {f.get('Чем доказано','—')} | источник: {f.get('источник','—')}")
    print(f"  источники компании: {k['istochniki_kompanii']}")


def main():
    fajly = [a for a in sys.argv[1:] if a.endswith('.json')]
    tolko = [a for a in sys.argv[1:] if a.isdigit()]
    for p in fajly:
        d = json.load(open(p, encoding='utf-8'))
        pary = d.items() if isinstance(d, dict) else [('', d)]
        for _, spisok in pary:
            for x in spisok:
                if not x.get('est'):
                    continue
                if tolko and x['inn'] not in tolko:
                    continue
                pokazat(x['inn'], R.razobrat(x['telo']))


if __name__ == '__main__':
    main()
