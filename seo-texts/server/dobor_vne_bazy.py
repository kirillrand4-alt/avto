# -*- coding: utf-8 -*-
r"""Компании, найденные ВНЕ базы, — залить и добрать им реквизиты.

Владелец 16.08: «давай, у нас база рассылки основана на предположении что вот эти
ОКВЭДы нам подходят, то есть может быть их меньше чем нужно».

Откуда берутся. Обход уходил на чужие сайты; в подвале такой страницы стоит ИНН
её настоящего хозяина. 216 таких ИНН не нашлись в нашей базе — это живые
предприятия, у которых сайт и контакты у нас УЖЕ скачаны, а строки нет.

Что здесь делается:
  1. --zalit      строка в companies: ИНН, сайт, заголовок сайта, пометка
                  источника. Направление (division) НЕ ставим: пока неизвестно,
                  наши ли они, и в кампанию попасть не должны;
  2. --rekvizity  имя, ОГРН и ПОЛНЫЙ список ОКВЭД через checko (тот же путь, что
                  и у остальной базы). Пишем сразу в enrich.db после каждой пачки:
                  прошлый прогон checko отдавал результат только в возвращаемый
                  JSON, и рестарт песочницы его терял;
  3. --stat       сколько из них попадает в 77 целевых кодов владельца, а сколько
                  мимо — и какие коды мимо чаще всего. Это и есть ответ на
                  «может быть их меньше чем нужно».

    python dobor_vne_bazy.py --zalit
    python dobor_vne_bazy.py --rekvizity [сколько]
    python dobor_vne_bazy.py --stat
"""
import json
import os
import subprocess
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ИСТОЧНИК = os.path.join(DIR, 'hozyaeva_vne_bazy.jsonl')
ЛОГ = os.path.join(DIR, 'dobor_vne_bazy.jsonl')
МЕТКА = 'вне-базы-инн-со-страницы'
PY = r'C:\Program Files\Python311\python.exe'
ОПЫ = os.path.join(DIR, 'enrich_contacts.py')


def _бд():
    c = sqlite3.connect(BD, timeout=60)
    for колонка in ('istochnik_kompanii TEXT',):
        try:
            c.execute('ALTER TABLE companies ADD COLUMN %s' % колонка)
        except Exception:  # noqa: BLE001
            pass
    return c


def залить():
    if not os.path.exists(ИСТОЧНИК):
        return {'нет файла': ИСТОЧНИК}
    видели, строки = set(), []
    for s in open(ИСТОЧНИК, encoding='utf-8'):
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(d.get('inn') or '').strip()
        if inn and inn not in видели:
            видели.add(inn)
            строки.append(d)
    c = _бд()
    итог = {'в_файле': len(строки), 'уже_были': 0, 'залито': 0}
    for d in строки:
        inn = str(d['inn'])
        if c.execute('select 1 from companies where inn=?', (inn,)).fetchone():
            итог['уже_были'] += 1
            continue
        c.execute("INSERT INTO companies(inn, site, site_title, site_source, "
                  "istochnik_kompanii, updated_at) VALUES(?,?,?,?,?,?)",
                  (inn, d.get('домен', ''), (d.get('заголовок') or '')[:200],
                   'инн-на-странице', МЕТКА, time.strftime('%Y-%m-%dT%H:%M:%S')))
        итог['залито'] += 1
    c.commit()
    c.close()
    return итог


def _checko(инны):
    """Вызвать оп checko_okveds тем же путём, каким его зовёт раннер."""
    p = subprocess.run([PY, ОПЫ], input=json.dumps({'op': 'checko_okveds', 'inns': инны},
                                                   ensure_ascii=False),
                       capture_output=True, text=True, encoding='utf-8', timeout=900)
    i = p.stdout.find('{')
    if i < 0:
        return []
    return (json.loads(p.stdout[i:]) or {}).get('results') or []


def реквизиты(сколько=250, пачка=25, кому='вне-базы'):
    """Добрать имя, ОГРН и полный ОКВЭД.

    кому='вне-базы'  — только что залитые строки (у них нет вообще ничего);
    кому='с-уликой'  — ЛЮБАЯ компания, у которой паспорт показывает сжатый воздух
                       или газы, а ОКВЭДа в базе нет. Их 563, и это узкое место
                       отбора: владелец судит по улике с сайта, но пока в строке
                       нет кода, компанию нечем сопоставить с его картой.
    """
    c = _бд()
    if кому == 'с-уликой':
        нужны = [str(r[0]) for r in c.execute(
            "select k.inn from companies k join site_facts f on f.inn=k.inn "
            "where coalesce(f.facts_json,'')<>'' and coalesce(k.okved,'')='' "
            "limit ?", (сколько,))]
    else:
        нужны = [str(r[0]) for r in c.execute(
            "select inn from companies where istochnik_kompanii=? and coalesce(name,'')='' "
            "limit ?", (МЕТКА, сколько))]
    c.close()
    итог = {'взяли': len(нужны), 'с_именем': 0, 'с_окведом': 0, 'сбоев': 0}
    for i in range(0, len(нужны), пачка):
        часть = нужны[i:i + пачка]
        try:
            рез = _checko(часть)
        except Exception as e:  # noqa: BLE001
            итог['сбоев'] += len(часть)
            итог['последний_сбой'] = str(e)[:120]
            continue
        c = _бд()
        for r in рез:
            # имя, основной ОКВЭД и направление оп кладёт в companies сам (durable);
            # здесь дописываем полный список кодов — его он держит только в stage_log
            все = ' '.join(r.get('okveds_all') or [])
            основной = r.get('okved_main') or ''
            c.execute("UPDATE companies SET name=coalesce(nullif(?,''),name), "
                      "ogrn=coalesce(nullif(?,''),ogrn), okved=coalesce(nullif(?,''),okved), "
                      "okved_all=coalesce(nullif(?,''),okved_all), updated_at=? WHERE inn=?",
                      (r.get('name') or '', r.get('ogrn') or '', основной, все,
                       time.strftime('%Y-%m-%dT%H:%M:%S'), r['inn']))
            итог['с_именем'] += 1 if r.get('name') else 0
            итог['с_окведом'] += 1 if все else 0
        c.commit()
        c.close()
        with open(ЛОГ, 'a', encoding='utf-8') as f:
            for r in рез:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    return итог


def _цель(код, карта):
    """Код (или любой его префикс) есть в 77 целевых кодах владельца?"""
    к = (код or '').split()[0] if код else ''
    while к:
        if к in карта:
            return карта[к]
        if '.' not in к:
            return None
        к = к.rsplit('.', 1)[0]
    return None


def статистика():
    import enrich_db as EDB
    карта = EDB.OKVED_DIRECTIONS
    c = _бд()
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select inn, coalesce(name,'') name, coalesce(okved,'') okved, "
        "coalesce(okved_all,'') okved_all, coalesce(site,'') site "
        "from companies where istochnik_kompanii=?", (МЕТКА,)))
    c.close()
    итог = {'всего': len(строки), 'без_реквизитов': 0, 'цель_по_основному': 0,
            'цель_только_в_допах': 0, 'мимо': 0}
    мимо_коды, примеры_цель, примеры_мимо = {}, [], []
    for r in строки:
        if not r['okved'] and not r['okved_all']:
            итог['без_реквизитов'] += 1
            continue
        осн = _цель(r['okved'], карта)
        доп = None
        if not осн:
            for к in (r['okved_all'] or '').split():
                доп = _цель(к, карта)
                if доп:
                    break
        if осн or доп:
            итог['цель_по_основному' if осн else 'цель_только_в_допах'] += 1
            if len(примеры_цель) < 8:
                примеры_цель.append({'инн': str(r['inn']), 'имя': r['name'][:45],
                                     'сайт': r['site'], 'оквэд': r['okved'][:45],
                                     'направление': (осн or доп)[0]})
        else:
            итог['мимо'] += 1
            к = (r['okved'] or '?').split()[0]
            мимо_коды[к] = мимо_коды.get(к, 0) + 1
            if len(примеры_мимо) < 8:
                примеры_мимо.append({'инн': str(r['inn']), 'имя': r['name'][:45],
                                     'оквэд': r['okved'][:55]})
    итог['мимо_топ_кодов'] = sorted(мимо_коды.items(), key=lambda x: -x[1])[:12]
    итог['примеры_цель'] = примеры_цель
    итог['примеры_мимо'] = примеры_мимо
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        и = статистика()
        print(json.dumps({'примеры_цель': и.pop('примеры_цель', []),
                          'примеры_мимо': и.pop('примеры_мимо', [])},
                         ensure_ascii=False, indent=1))
        print(json.dumps(и, ensure_ascii=False, indent=1))
    elif a[0] == '--zalit':
        print(json.dumps(залить(), ensure_ascii=False, indent=1))
    elif a[0] == '--rekvizity':
        print(json.dumps(реквизиты(int(a[1]) if len(a) > 1 else 250),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--rekvizity-uliki':
        print(json.dumps(реквизиты(int(a[1]) if len(a) > 1 else 600, кому='с-уликой'),
                         ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
