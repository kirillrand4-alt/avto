# -*- coding: utf-8 -*-
"""Как test@mail.ru стал контактом ООО «ДЕСТРОЙ» и как по нему ушло письмо."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ИНН = '5406743528'
АДРЕС = 'test@mail.ru'
итог = {}
e = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
e.row_factory = sqlite3.Row
k = e.execute('select inn, name, site, cand_site, best_email, activity, okved, '
              'region, updated_at from companies where inn=?', (ИНН,)).fetchone()
итог['карточка'] = {kk: k[kk] for kk in k.keys()} if k else 'нет карточки'
итог['почты_компании'] = [{kk: r[kk] for kk in r.keys()} for r in e.execute(
    "select email, coalesce(role,'') role, coalesce(source,'') ist, "
    "coalesce(source_url,'') url, coalesce(pometka,'') pom, coalesce(razdel,'') razd, "
    'coalesce(updated_at,\'\') upd from emails where inn=?', (ИНН,))]
итог['где_ещё_встречается_адрес'] = [dict(zip(('inn', 'source', 'url'), r)) for r in e.execute(
    "select inn, coalesce(source,''), coalesce(source_url,'') from emails "
    'where lower(email)=?', (АДРЕС,))]
итог['всего_тестовых_в_базе'] = [dict(zip(('email', 'сколько'), r)) for r in e.execute(
    "select lower(email), count(*) n from emails where lower(email) in "
    "('test@mail.ru','test@test.ru','test@example.com','mail@mail.ru','info@mail.ru',"
    "'admin@mail.ru','123@mail.ru','test@gmail.com','test@yandex.ru') "
    'group by 1 order by n desc')]
e.close()
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
r = s.execute("select id, email, coalesce(inn,'') inn, coalesce(source,'') src, "
              "coalesce(segment,'') seg, coalesce(created_at,'') cr, "
              "coalesce(extra_json,'') ex from recipients where lower(email)=?",
              (АДРЕС,)).fetchone()
итог['получатель_в_панели'] = {kk: (str(r[kk])[:160] if r[kk] is not None else None)
                                for kk in r.keys()} if r else 'нет'
итог['очередь_подтверждения'] = [{kk: (str(x[kk])[:120] if x[kk] is not None else None)
                                  for kk in ('id', 'status', 'campaign_id', 'email',
                                             'decided_by', 'decided_at', 'reason')}
                                 for x in s.execute(
    "select * from confirm_reviews where lower(coalesce(email,''))=?", (АДРЕС,))]
итог['аудит_по_адресу'] = [dict(zip(('action', 'detail', 'when'), r)) for r in s.execute(
    "select action, substr(coalesce(detail_json,''),1,140), created_at from audit_log "
    "where coalesce(detail_json,'') like ? order by id desc limit 8", ('%' + АДРЕС + '%',))]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4600])
