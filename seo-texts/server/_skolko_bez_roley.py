# -*- coding: utf-8 -*-
r"""Кому роли телефонов ещё можно добыть: есть страницы, а ролей нет."""
import json
import os
import sqlite3

КЕШ = r'C:\seostat\drop\pagecache'
в_кэше = {n.split('.')[0] for n in os.listdir(КЕШ) if n.endswith('.json.gz')}
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
с_ролью = {str(r[0]) for r in c.execute(
    "select distinct inn from phone_contacts where coalesce(role,'') not in ('','общий')")}
с_номером = {str(r[0]) for r in c.execute('select distinct inn from phone_contacts')}
прошли_провайдера = {str(r[0]) for r in c.execute(
    "select distinct inn from stage_log where stage in ('phone','email')")}
c.close()
print(json.dumps({
    'компаний_в_кэше_страниц': len(в_кэше),
    'из_них_с_ролью_хоть_у_одного_телефона': len(в_кэше & с_ролью),
    'из_них_с_телефонами_но_без_ролей': len((в_кэше & с_номером) - с_ролью),
    'из_них_вообще_без_телефонов': len(в_кэше - с_номером),
    'проходили_провайдерское_извлечение': len(в_кэше & прошли_провайдера),
    'в_кэше_но_провайдер_не_читал': len(в_кэше - прошли_провайдера),
}, ensure_ascii=False, indent=1))
