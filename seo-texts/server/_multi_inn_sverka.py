# -*- coding: utf-8 -*-
"""Сверка цифр соседа: домены на несколько ИНН — сколько ЖИВЫХ привязок сейчас.

Сосед насчитал 3337 карточек под 1437 мульти-ИНН доменами. Мы этот класс уже
чистили (ploshchadki + много_чужих_инн + sverka_privyazki). Смотрим: в каком
поле сидят эти привязки (site / cand_site), сколько уже в карантине
(otkloneno_json), и живы ли его примеры (tenderguru, азимуты, автошкола).
"""
import json
import os
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, r'C:\sender\server', r'C:\sender'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL  # noqa: E402

ENRICH = r'C:\sender\enrich.db'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    по_домену = {}
    for r in c.execute("select inn, coalesce(nullif(site,''),'') s, "
                       "coalesce(nullif(cand_site,''),'') cs from companies"):
        for поле, знач in (('site', r['s']), ('cand', r['cs'])):
            д = PL.домен(знач) if знач else ''
            if not д:
                continue
            по_домену.setdefault(д, []).append((str(r['inn']), поле, False))
    мульти = {д: з for д, з in по_домену.items()
              if len({и for и, _, _ in з}) >= 2}
    итог = {'мульти_доменов': len(мульти),
            'карточек_под_ними': sum(len({и for и, _, _ in з})
                                     for з in мульти.values())}
    сайт = канд = в_блэклисте = 0
    for д, з in мульти.items():
        if PL.площадка_ли(д) if hasattr(PL, 'площадка_ли') else False:
            в_блэклисте += 1
        for _, поле, _ in з:
            if поле == 'site':
                сайт += 1
            else:
                канд += 1
    итог['привязок_в_site'] = сайт
    итог['кандидатов_в_cand_site'] = канд
    топ = sorted(мульти.items(), key=lambda kv: -len({и for и, _, _ in kv[1]}))
    итог['топ'] = [{'домен': д, 'инн': len({и for и, _, _ in з}),
                    'site': sum(1 for _, п, _ in з if п == 'site'),
                    'cand': sum(1 for _, п, _ in з if п == 'cand')}
                   for д, з in топ[:10]]
    for пример in ('tenderguru.ru', 'azimuthotels.com', 'avtoschool-vektor.ru',
                   'check.tochka.com', 'basis.myseldon.com'):
        з = по_домену.get(пример) or []
        итог['пример_' + пример] = {
            'инн': len({и for и, _, _ in з}),
            'в_site': sum(1 for _, п, _ in з if п == 'site'),
            'в_cand': sum(1 for _, п, _ in з if п == 'cand')}
    c.close()
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
