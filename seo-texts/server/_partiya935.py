# -*- coding: utf-8 -*-
"""Партия-935: где застряли 757 получателей на пути к очереди проверки."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['получателей'] = s.execute(
    "select count(*) from recipients where source='партия-935'").fetchone()[0]
итог['по_кампаниям_в_очереди'] = [dict(r) for r in s.execute(
    "select cr.campaign_id, cr.status, count(*) skolko from confirm_reviews cr "
    "join recipients r on r.id=cr.recipient_id where r.source='партия-935' "
    'group by 1,2')]
итог['писем_сгенерировано'] = s.execute(
    "select count(*) from ai_letter_log l join recipients r on r.id=l.recipient_id "
    "where r.source='партия-935'").fetchone()[0]
итог['в_send_log'] = s.execute(
    "select count(*) from send_log sl join recipients r on r.inn=sl.inn "
    "where r.source='партия-935'").fetchone()[0]
итог['колонки_суппрессии'] = [r[1] for r in s.execute('pragma table_info(suppression)')]
итог['статусы_валидации'] = [dict(r) for r in s.execute(
    "select coalesce(valid_status,'(пусто)') st, count(*) skolko from recipients "
    "where source='партия-935' group by 1 order by skolko desc limit 8")]
итог['ролевых'] = s.execute(
    "select count(*) from recipients where source='партия-935' and role_based=1").fetchone()[0]
итог['есть_инн'] = s.execute(
    "select count(*) from recipients where source='партия-935' and coalesce(inn,'')<>''"
).fetchone()[0]
итог['примеры'] = [dict(r) for r in s.execute(
    "select email, coalesce(company_name,'') name, coalesce(inn,'') inn, "
    "coalesce(valid_status,'') vs, coalesce(segment,'') seg from recipients "
    "where source='партия-935' limit 5")]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2800])
