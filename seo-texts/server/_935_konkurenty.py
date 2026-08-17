# -*- coding: utf-8 -*-
"""Есть ли в «Партии 935» конкуренты и держит ли их стоп-лист панели.

Конкурент по карточке: companies.is_competitor (вердикт обхода: сам производит/
продаёт компрессоры, генераторы, фотосепараторы, рентген-инспекцию). Панельный
стоп-лист: таблица suppression. Опасны те, кто конкурент по карточке, но в
стоп-лист не попал — им кампания сгенерирует письмо.
"""
import json
import sqlite3
import sys

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    s.row_factory = sqlite3.Row
    группа = {}
    for r in s.execute("select id, coalesce(inn,'') inn, email, "
                       "coalesce(extra_json,'') ex from recipients "
                       "where extra_json like '%Партия 935%'"):
        инн = ''.join(c for c in r['inn'] if c.isdigit())
        if инн:
            группа.setdefault(инн, []).append(r['email'])
    итог = {'в_группе_компаний': len(группа)}
    итог['suppression_колонки'] = [r[1] for r in s.execute(
        'pragma table_info(suppression)')]
    стоп_инн = {''.join(c for c in str(r[0]) if c.isdigit()): (r[1] or '')
                for r in s.execute("select value, reason from suppression "
                                   "where scope='inn'")}
    s.close()

    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    e.row_factory = sqlite3.Row
    конкуренты = {}
    # фильтр в питоне: в SQLite int 0 не равен строке '0', и SQL-сравнение
    # пропускало всех подряд (первый прогон посчитал конкурентами всю группу)
    for r in e.execute("select inn, coalesce(name,'') name, is_competitor k "
                       'from companies'):
        if str(r['k'] or '').strip().lower() in ('1', 'true', 'да', 'yes'):
            конкуренты[str(r['inn'])] = (r['k'], r['name'])
    e.close()

    в_группе_конк = {и: конкуренты[и] for и in группа if и in конкуренты}
    прикрыты = {и: стоп_инн[и] for и in в_группе_конк if и in стоп_инн}
    дыры = {и: в_группе_конк[и] for и in в_группе_конк if и not in стоп_инн}
    итог['конкурентов_в_карточках_всего'] = len(конкуренты)
    итог['конкурентов_в_группе'] = len(в_группе_конк)
    итог['из_них_в_стоп-листе'] = len(прикрыты)
    итог['ДЫРА_конкурент_без_стоп-листа'] = len(дыры)
    итог['примеры_дыры'] = [
        {'инн': и, 'вердикт': str(v[0])[:60], 'имя': v[1][:45],
         'почты': группа[и][:2]} for и, v in list(дыры.items())[:10]]
    итог['причины_стопа_прикрытых'] = {}
    for и, п in прикрыты.items():
        итог['причины_стопа_прикрытых'][п or '(пусто)'] = \
            итог['причины_стопа_прикрытых'].get(п or '(пусто)', 0) + 1
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
