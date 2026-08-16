# -*- coding: utf-8 -*-
r"""Убрать из базы привязки к площадкам и паспорта, собранные по ним.

Замер 16.08: 818 привязок ведут на площадки из списка, 213 из них стоят ГЛАВНЫМ
сайтом компании. Лидер — check.tochka.com (421 привязка): страница проверки
контрагента в банке, где ИНН компании напечатан крупно, поэтому она проходила
нашу же проверку «ИНН на сайте» лучше настоящего завода.

Что делаем: адрес площадки убираем из site/cand_site, паспорт, собранный по этим
страницам, уводим в карантин (facts_json пустеет, текст остаётся в otkloneno_json).
Ничего не удаляем безвозвратно — снятые адреса пишутся в jsonl на сервере, вернуть
можно руками.

    python chistka_ploshchadok.py --stat       посчитать, ничего не трогая
    python chistka_ploshchadok.py --primenit   снять привязки и убрать паспорта
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЛОГ = os.path.join(DIR, 'chistka_ploshchadok.jsonl')


def найти():
    c = sqlite3.connect(BD, timeout=60)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select inn, coalesce(name,'') name, coalesce(site,'') site, "
        "coalesce(cand_site,'') cand, coalesce(verified,'') verified, "
        "coalesce(best_email,'') best_email from companies "
        "where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''"))
    паспорта = {str(r[0]) for r in c.execute(
        "select inn from site_facts where coalesce(facts_json,'')<>''")}
    c.close()
    находки = []
    for r in строки:
        for поле, url in (('site', r['site']), ('cand_site', r['cand'])):
            п = PL.из_списка(url)
            if п:
                находки.append({'inn': str(r['inn']), 'имя': r['name'][:60],
                                'поле': поле, 'url': url, 'площадка': п,
                                'verified': r['verified'],
                                'паспорт': str(r['inn']) in паспорта,
                                'почта': bool(r['best_email'])})
    return находки


def применить():
    находки = найти()
    c = sqlite3.connect(BD, timeout=60)
    итог = {'снято_site': 0, 'снято_cand_site': 0, 'паспортов_в_карантин': 0}
    for н in находки:
        поле = н['поле']
        c.execute("UPDATE companies SET %s='', updated_at=? WHERE inn=? AND %s=?"
                  % (поле, поле), (time.strftime('%Y-%m-%dT%H:%M:%S'), н['inn'], н['url']))
        итог['снято_' + поле] += 1
        if н['паспорт']:
            n = c.execute(
                "UPDATE site_facts SET otkloneno_json=facts_json, facts_json='', "
                "privyazka=?, note=? WHERE inn=? AND coalesce(facts_json,'')<>''",
                ('площадка: ' + н['площадка'],
                 'паспорт собран по странице площадки (%s) — в карантине' % н['площадка'],
                 н['inn'])).rowcount
            итог['паспортов_в_карантин'] += n
    c.commit()
    c.close()
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for н in находки:
            f.write(json.dumps(н, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    итог['всего_находок'] = len(находки)
    return итог


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        находки = найти()
        по_площадкам = {}
        for н in находки:
            по_площадкам[н['площадка']] = по_площадкам.get(н['площадка'], 0) + 1
        print(json.dumps({
            'всего': len(находки),
            'главным_сайтом': sum(1 for н in находки if н['поле'] == 'site'),
            'с_паспортом': sum(1 for н in находки if н['паспорт']),
            'по_площадкам': sorted(по_площадкам.items(), key=lambda x: -x[1])[:15],
            'примеры': находки[:8]}, ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
