# -*- coding: utf-8 -*-
r"""Кто лучше собирает новости — луна или хайку. Замер на одних и тех же сайтах.

Владелец 17.08: «новости на хайку, мы замеряли что так лучше?». Замер был 13.08 и
записан в site_facts: на 20 компаниях луна дала 2 новости, хайку 12, из них 11
подтверждены дословно. Выборка маленькая, делала его прошлая сессия, и было это
ДО сегодняшних правок промпта — поэтому перепроверяем.

Меряем три вещи, потому что «больше новостей» само по себе ничего не значит:
    сколько     — новостей на компанию;
    правда ли   — доля подтверждённых дословным поиском по скачанным страницам;
    свежесть    — доля новостей за последние 12 месяцев (старая новость в письме
                  хуже, чем никакой: «почему пишу сейчас» из неё не построить).

Обе модели получают ОДИН И ТОТ ЖЕ промпт и одни и те же страницы. В базу ничего
не пишем — это замер, а не сбор.

    python zamer_novostey.py [сколько компаний]
"""
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import site_facts as SF           # noqa: E402
import pasport_sverka as PS       # noqa: E402

МОДЕЛИ = ('gpt-5.6-luna', 'claude-haiku-4-5')
ИТОГ = os.path.join(DIR, 'zamer_novostey.jsonl')


def кандидаты(сколько):
    """Компании, у которых на страницах ЕСТЬ следы ленты — иначе мерить нечего."""
    c = sqlite3.connect('file:%s?mode=ro' % SF.BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select f.inn, coalesce(k.name,'') name, coalesce(f.site,'') site "
        "from site_facts f join companies k on k.inn=f.inn "
        "where coalesce(f.facts_json,'')<>'' and coalesce(f.format,0)>=2 "
        'order by f.ts desc limit 400'))
    c.close()
    из = []
    for r in строки:
        stranicy = SF._stranicy(str(r['inn']))
        if not stranicy:
            continue
        текст = ' '.join(t for _u, t in stranicy)
        if not SF._SLED_NOVOSTI.search(текст):
            continue
        из.append({'inn': str(r['inn']), 'name': r['name'], 'site': r['site'],
                   'stranicy': stranicy})
        if len(из) >= сколько:
            break
    return из


def _свежая(дата):
    """Новость за последние 12 месяцев?"""
    г_м = SF._data_novosti(дата)
    if not г_м:
        return None
    год, месяц = г_м
    сейчас = time.localtime()
    возраст = (сейчас.tm_year - год) * 12 + (сейчас.tm_mon - месяц)
    return 0 <= возраст <= 12


def спросить(клиент, k, модель):
    import gen_provider as GP
    tekst = '\n\n'.join('--- %s\n%s' % (u, t) for u, t in k['stranicy'])
    vopros = SF.PROMPT_NOVOSTI % {'name': k['name'][:80], 'stranicy': tekst}
    try:
        msg = GP.call(клиент, [{'role': 'user', 'content': vopros}],
                      model=модель, attempts=2)
        d = GP.parse_json(msg)
    except Exception as e:  # noqa: BLE001
        return {'сбой': str(e)[:100], 'новости': []}
    return {'новости': d.get('новости') or []}


def замер(сколько=40, потоков=8):
    import gen_provider as GP
    сп = кандидаты(сколько)
    if not сп:
        return {'некого мерить': True}
    клиент = GP.make_client()
    итог = {м: {'компаний': 0, 'новостей': 0, 'подтверждено': 0, 'свежих': 0,
                'без_даты': 0, 'сбоев': 0, 'пусто': 0} for м in МОДЕЛИ}

    def одна(k):
        текст = PS._tekst(k['inn'])
        строка = {'inn': k['inn'], 'имя': k['name'][:40]}
        for м in МОДЕЛИ:
            r = спросить(клиент, k, м)
            строка[м] = r
            б = итог[м]
            б['компаний'] += 1
            if r.get('сбой'):
                б['сбоев'] += 1
                continue
            нов = r['новости']
            if not нов:
                б['пусто'] += 1
            for n in нов:
                б['новостей'] += 1
                заг = str(n.get('заголовок') or '')
                if заг and текст and PS._podtverzhdena(заг.lower().replace('ё', 'е'), текст):
                    б['подтверждено'] += 1
                с = _свежая(n.get('дата'))
                if с is None:
                    б['без_даты'] += 1
                elif с:
                    б['свежих'] += 1
        return строка

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=потоков) as ex, \
            open(ИТОГ, 'a', encoding='utf-8') as f:
        for строка in ex.map(одна, сп):
            f.write(json.dumps(строка, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    for м, б in итог.items():
        б['новостей_на_компанию'] = round(б['новостей'] / max(1, б['компаний']), 1)
        б['доля_подтверждённых'] = round(б['подтверждено'] / max(1, б['новостей']), 2)
        б['доля_свежих'] = round(б['свежих'] / max(1, б['новостей']), 2)
    итог['секунд'] = round(time.time() - t0)
    return итог


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
    print(json.dumps(замер(n), ensure_ascii=False, indent=1))
