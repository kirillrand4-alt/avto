# -*- coding: utf-8 -*-
r"""Честная цена бесплатного прохода: кому он реально что-то даст.

Прошлая прикидка («19-20 тысяч компаний без номеров») считала по всем ИНН
кэша, а больше половины из них в companies не заведены вовсе. Пересчитываем.
"""
import json
import os
import sqlite3

в_кэше = {n.split('.')[0] for n in os.listdir(r'C:\seostat\drop\pagecache')
          if n.endswith('.json.gz')}
e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
все = {str(r[0]) for r in e.execute('select inn from companies')}
с_номером_в_таблице = {str(r[0]) for r in e.execute(
    'select distinct inn from phone_contacts')}
со_списком = {str(r[0]) for r in e.execute(
    "select inn from companies where coalesce(phones,'') not in ('','[]')")}
с_ролью = {str(r[0]) for r in e.execute(
    "select distinct inn from phone_contacts where coalesce(role,'') "
    "not in ('','общий','общий (со страницы)','мобильный','номер предприятия')")}
e.close()
наши = в_кэше & все
print(json.dumps({
    'кэш_и_есть_в_companies': len(наши),
    'из_них_без_строк_в_phone_contacts': len(наши - с_номером_в_таблице),
    'из_них_без_номеров_вовсе': len(наши - с_номером_в_таблице - со_списком),
    'из_них_без_ОСМЫСЛЕННОЙ_роли': len(наши - с_ролью),
    'ИНН_кэша_вне_companies': len(в_кэше - все),
}, ensure_ascii=False, indent=1))
