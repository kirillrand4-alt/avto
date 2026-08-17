# -*- coding: utf-8 -*-
"""Партии загрузки (recipients.source) и их путь до очереди проверки."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['партии_по_source'] = [dict(r) for r in s.execute(
    "select coalesce(source,'(пусто)') partiya, count(*) skolko, min(created_at) s_kogda "
    'from recipients group by 1 order by skolko desc limit 12')]
итог['писем_сгенерировано'] = s.execute('select count(*) from ai_letter_log').fetchone()[0]
итог['в_очереди_проверки_всего'] = s.execute('select count(*) from confirm_reviews').fetchone()[0]
итог['по_статусам'] = [dict(r) for r in s.execute(
    'select status, count(*) skolko from confirm_reviews group by 1 order by skolko desc')]
# путь партии: сколько её получателей дошло до очереди проверки и до отправки
итог['по_партиям'] = [dict(r) for r in s.execute(
    "select coalesce(r.source,'(пусто)') partiya, count(distinct r.id) poluchateley, "
    "count(distinct cr.id) v_ocheredi, "
    "sum(case when cr.status='sent' then 1 else 0 end) otpravleno, "
    "sum(case when cr.status='pending' then 1 else 0 end) zhdut "
    "from recipients r left join confirm_reviews cr on cr.recipient_id=r.id "
    'group by 1 order by poluchateley desc limit 10')]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
