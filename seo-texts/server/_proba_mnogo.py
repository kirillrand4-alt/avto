# -*- coding: utf-8 -*-
r"""Проверка: видит ли поиск таблицу и отсеивает ли по ней."""
import json, os, sys
sys.path.insert(0, r'C:\sender\server'); os.chdir(r'C:\sender\server')
import poisk_saytov as PS
import ploshchadki as PL
м = PS.мнoгokompaniynye()
проба = ['sensus.kz', 'prodoctorov.ru', 'web.archive.org', 'tatarstan.ru',
         'check.tochka.com', 'zavod-realnyy-nesushchestvuyushchiy.ru']
print(json.dumps({
    'в_таблице': len(м),
    'разбор': {д: ('список площадок' if PL.из_списка(д)
                   else 'многокомпанийный' if д in м else 'годен')
               for д in проба}}, ensure_ascii=False, indent=1))
