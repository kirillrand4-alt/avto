# -*- coding: utf-8 -*-
"""Какие сегменты и группы уже есть в панели — чтобы новая партия легла так же."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['сегменты'] = [dict(r) for r in s.execute(
    "select coalesce(segment,'(пусто)') seg, count(*) skolko from recipients "
    'group by 1 order by skolko desc limit 12')]
итог['группы_source'] = [dict(r) for r in s.execute(
    "select coalesce(source,'(пусто)') grp, count(*) skolko from recipients "
    'group by 1 order by skolko desc limit 8')]
итог['партия_935_пример'] = [dict(r) for r in s.execute(
    "select email, coalesce(company_name,'') name, coalesce(inn,'') inn, "
    "coalesce(segment,'') seg, coalesce(okved,'') okved, coalesce(region,'') reg, "
    "coalesce(contact_name,'') imya, coalesce(pxr,'') pxr, "
    "coalesce(priority_total,'') pt from recipients where source='партия-935' limit 3")]
итог['настройка_segment_division'] = [dict(r) for r in s.execute(
    "select value from panel_settings where key='segment_division'")]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
