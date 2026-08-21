# -*- coding: utf-8 -*-
r"""Сходятся ли два счёта «непрошедших»: 19 629 против 1 944.

Разница подозрительна: один счёт брал все ИНН из кэша, другой — только те,
у кого в companies записан сайт. Проверяем, сколько ИНН кэша вообще есть в
companies.
"""
import json
import os
import sqlite3

в_кэше = {n.split('.')[0] for n in os.listdir(r'C:\seostat\drop\pagecache')
          if n.endswith('.json.gz')}
e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
все = {str(r[0]) for r in e.execute('select inn from companies')}
с_сайтом = {str(r[0]) for r in e.execute(
    "select inn from companies where coalesce(site,'')<>'' or coalesce(cand_site,'')<>''")}
прошли = {str(r[0]) for r in e.execute(
    "select distinct inn from stage_log where stage in ('email','phone')")}
e.close()
print(json.dumps({
    'ИНН_в_кэше': len(в_кэше),
    'из_них_есть_в_companies': len(в_кэше & все),
    'из_них_НЕТ_в_companies': len(в_кэше - все),
    'в_кэше_и_в_companies_и_с_сайтом': len(в_кэше & с_сайтом),
    'в_кэше_не_прошли_извлечение': len(в_кэше - прошли),
    'в_кэше_в_companies_не_прошли': len((в_кэше & все) - прошли),
    'в_кэше_с_сайтом_не_прошли': len((в_кэше & с_сайтом) - прошли),
}, ensure_ascii=False, indent=1))
