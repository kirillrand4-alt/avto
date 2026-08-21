# -*- coding: utf-8 -*-
r"""Два вопроса владельца 21.08: телефоны «Партии 935» с ролями? и кого
провайдер вообще не смотрел?

Считаем по компаниям группы (не по адресам) и отдельно — охват извлечения по
всей базе, с разбивкой «есть сайт / есть страницы в кэше».
"""
import json
import os
import sqlite3

КЕШ = r'C:\seostat\drop\pagecache'
ГРУППА = 'Партия 935'

s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
инн_935 = set()
for инн, ex in s.execute("select coalesce(inn,''), coalesce(extra_json,'') "
                         'from recipients'):
    if ГРУППА in ex:
        ц = ''.join(c for c in str(инн) if c.isdigit())
        if ц:
            инн_935.add(ц)
s.close()

e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
e.row_factory = sqlite3.Row
с_телефоном, с_ролью_тел = set(), set()
роли_тел = {}
for r in e.execute("select inn, coalesce(role,'') role from phone_contacts"):
    и = str(r['inn'])
    с_телефоном.add(и)
    if r['role'] and r['role'] != 'общий':
        с_ролью_тел.add(и)
        if и in инн_935:
            роли_тел[r['role']] = роли_тел.get(r['role'], 0) + 1
список_номеров = {str(r[0]) for r in e.execute(
    "select inn from companies where coalesce(phones,'') not in ('','[]')")}
прошли_почта = {str(r[0]) for r in e.execute(
    "select distinct inn from stage_log where stage='email'")}
прошли_тел = {str(r[0]) for r in e.execute(
    "select distinct inn from stage_log where stage='phone'")}
всего_компаний = e.execute('select count(*) from companies').fetchone()[0]
с_сайтом = {str(r[0]) for r in e.execute(
    "select inn from companies where coalesce(site,'')<>'' "
    "or coalesce(cand_site,'')<>''")}
e.close()
в_кэше = {n.split('.')[0] for n in os.listdir(КЕШ) if n.endswith('.json.gz')}

d = {'партия_935': {
    'компаний': len(инн_935),
    'есть_телефон_в_phone_contacts': len(инн_935 & с_телефоном),
    'есть_номера_списком_в_companies': len(инн_935 & список_номеров),
    'ТЕЛЕФОН_С_РОЛЬЮ': len(инн_935 & с_ролью_тел),
    'прошли_извлечение_телефонов': len(инн_935 & прошли_тел),
    'прошли_извлечение_почт': len(инн_935 & прошли_почта),
}, 'роли_телефонов_935': dict(sorted(роли_тел.items(), key=lambda x: -x[1])[:10])}

прошли = прошли_почта | прошли_тел
d['охват_по_всей_базе'] = {
    'компаний_в_companies': всего_компаний,
    'прошли_извлечение_контактов': len(прошли),
    'НЕ_прошли': всего_компаний - len(прошли),
    'из_непрошедших_есть_сайт': len(с_сайтом - прошли),
    'из_непрошедших_страницы_уже_в_кэше': len((в_кэше & с_сайтом) - прошли),
    'из_непрошедших_сайта_нет': (всего_компаний - len(прошли)
                                 - len(с_сайтом - прошли)),
}
print(json.dumps(d, ensure_ascii=False, indent=1))
