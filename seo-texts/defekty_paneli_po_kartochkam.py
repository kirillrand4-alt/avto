# -*- coding: utf-8 -*-
"""Считает дефекты панели по снятым карточкам — те самые, что нашлись глазами.

Глазами найдено восемь классов дефектов на пяти карточках. Дальше вопрос не «есть ли они»,
а «на скольких карточках из скольких» — иначе чинить будут по анекдоту. Модуль берёт снимки
`panel_kartochki.py` и по каждому классу выдаёт число и примеры.

Классы (все проверяются по разметке, а не по впечатлению):
    провенанс-слэш   источник компании разрезан по «/» на имя и ссылку
    имя-пустышка     человек «Имя не установлено» показан как специалист
    директор-юрлицо  в поле «Директор» стоит ООО/АО, а не человек
    падеж            две записи одного человека, одна — фамилия в родительном падеже
    дубль-факта      одна процедура двумя фактами (разные пути ссылки, один номер)
    ликвидировано    статус ЕГРЮЛ LIQUIDATED при живом приоритете
    регион-пуст      регион «—» при заполненном адресе
    людей-ноль       фактов много, людей ноль (наша недоработка, не панели)
    суд-против-фактов  вердикт «нет», а в фактах тип «центробежная»
    мусор-не-та-машина в доказательствах только винтовые/поршневые/передвижные

Использование:
    python3 defekty_paneli_po_kartochkam.py снимок1.json снимок2.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import razbor_kartochki_paneli as R

NE_NASHA = ('винтов', 'поршнев', 'передвижн', 'дизельн')


def familiya(s):
    ch = re.sub(r'[^А-ЯЁа-яё ]', ' ', s or '').split()
    return ch[0].lower() if ch else ''


def osnova_familii(f):
    """«макеева» → «макеев»: съедается ровно одна конечная «а».

    Первая версия резала 'ва'/'на' целиком и давала 'макее' против 'макеев' — то есть НЕ
    склеивала как раз ту пару, ради которой писалась. Ошибка того же рода, что весь день:
    проверять надо на примере, о котором точно известно, что он должен совпасть.
    Ложные срабатывания (муж и жена Поповы) возможны и допустимы: это пометка к проверке.
    """
    return f[:-1] if len(f) >= 5 and f.endswith('а') else f


def po_kartochke(inn, k):
    """Список (класс, подробность) для одной карточки."""
    out = []
    for ist in k['istochniki_kompanii']:
        if 'Источник:' in ist and 'ссылки нет' in ist:
            out.append(('провенанс-слэш', ist[:80]))
            break
    for l in k['lyudi']:
        if 'не установлено' in l['chelovek'].lower():
            out.append(('имя-пустышка', f"{l['chelovek']} / {l['dolzhnost']}"))
    dr = k['rekvizity'].get('Директор') or ''
    if re.search(r'\b(ООО|АО|ПАО|ЗАО|ОБЩЕСТВО С ОГРАНИЧЕННОЙ)\b', dr):
        out.append(('директор-юрлицо', dr[:70]))
    # Дубль человека бывает ДВУХ разных сортов, и валить их в кучу нельзя: «Егоров С.Л.» и
    # «Егоров Сергей Леонидович» — одна и та же фамилия, разная полнота записи; «Макеева С.А.»
    # и «Макеев Сергей Александрович» — фамилия ИСКАЖЕНА родительным падежом. Первое чинится
    # склейкой, второе — правкой разбора у источника, иначе искажение поедет дальше.
    osnovy = defaultdict(list)
    for l in k['lyudi']:
        f = familiya(l['chelovek'])
        if f:
            osnovy[osnova_familii(f)].append((f, l['chelovek']))
    for _, spisok in osnovy.items():
        napisaniya = {c for _, c in spisok}
        if len(napisaniya) < 2:
            continue
        familii = {f for f, _ in spisok}
        klass = 'падеж-искажена-фамилия' if len(familii) > 1 else 'дубль-инициалы-и-полное-имя'
        out.append((klass, ' + '.join(sorted(napisaniya))))
    proc = defaultdict(list)
    for f in k['fakty']:
        m = re.search(r'/(\d{6,})-', f.get('ссылка') or '')
        if m:
            proc[m.group(1)].append(f.get('id') or '')
    for nom, ids in proc.items():
        if len(ids) > 1:
            out.append(('дубль-факта', f'процедура {nom}: факты {", ".join(ids)}'))
    if 'LIQUIDATED' in (k['rekvizity'].get('Статус ЕГРЮЛ') or ''):
        out.append(('ликвидировано', f"приоритет {k.get('приоритет')}"))
    if (k['rekvizity'].get('Регион') or '—') in ('—', '') and k.get('адрес', k['adres']):
        out.append(('регион-пуст', k['adres'][:60]))
    if not k['lyudi'] and (k.get('фактов') or '0') not in ('', '0'):
        out.append(('людей-ноль', f"фактов {k.get('фактов')}"))
    if k['sud'].startswith('суд: нет') and any('центробеж' in (f.get('Тип оборудования') or '')
                                               for f in k['fakty']):
        out.append(('суд-против-фактов', k['sud']))
    if k['fakty'] and all(
            any(s in ((f.get('Цитата') or '') + (f.get('Тип оборудования') or '')).lower()
                for s in NE_NASHA) for f in k['fakty']):
        out.append(('мусор-не-та-машина', (k['fakty'][0].get('Цитата') or '')[:70]))
    return out


def main():
    fajly = [a for a in sys.argv[1:] if a.endswith('.json')]
    kartochki = {}
    for p in fajly:
        d = json.load(open(p, encoding='utf-8'))
        pary = d.items() if isinstance(d, dict) else [('', d)]
        for _, spisok in pary:
            for x in spisok:
                if x.get('est') and x['inn'] not in kartochki:
                    kartochki[x['inn']] = R.razobrat(x['telo'])
    sch = Counter()
    primery = defaultdict(list)
    for inn, k in kartochki.items():
        for klass, podr in po_kartochke(inn, k):
            sch[klass] += 1
            if len(primery[klass]) < 4:
                primery[klass].append(f'{inn} {k["nazvanie"][:32]}: {podr}')
    print(f'карточек разобрано: {len(kartochki)}')
    for klass, n in sch.most_common():
        print(f'  {n:>4} / {len(kartochki)}  {klass}')
        for s in primery[klass]:
            print(f'          {s}')


if __name__ == '__main__':
    main()
