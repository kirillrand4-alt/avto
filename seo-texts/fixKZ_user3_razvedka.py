# -*- coding: utf-8 -*-
r"""fixKZ (21.10): панель КЦ – что сейчас у user3 и что ушло от него к user1/user2 по fixKR. Только чтение
(sqlite mode=ro). Пароли и хеши не читаются и не печатаются.

    python3 zapusk_na_servere.py fixKZ_user3_razvedka.py
"""
import collections
import sqlite3

SALES = r'C:\seostat\data\centro_sales.db'
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
s.row_factory = sqlite3.Row
kol_u = [r[1] for r in s.execute('PRAGMA table_info(users)')]
print('users, колонки:', [k for k in kol_u if 'pass' not in k.lower() and 'hash' not in k.lower()])
for r in s.execute('SELECT username, role, is_active FROM users ORDER BY username'):
    print('   ', dict(r))
print('назначения по пользователям:', dict(s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall()))
skr = "inn NOT IN (SELECT inn FROM hidden_item WHERE kind='company')"
print('из них не скрыты:', dict(s.execute('SELECT username, COUNT(*) FROM company_assignment WHERE %s GROUP BY 1' % skr).fetchall()))
print('ушло от user3 по fixKR (сейчас у кого / не скрыто):',
      dict(s.execute("SELECT username, COUNT(*) FROM company_assignment WHERE vladelec_do_fixKR='user3' GROUP BY 1").fetchall()),
      dict(s.execute("SELECT username, COUNT(*) FROM company_assignment WHERE vladelec_do_fixKR='user3' AND %s GROUP BY 1" % skr).fetchall()))
for t, pole in (('company_state', 'call_result'), ('company_comment', None), ('activity_log', 'action'), ('hidden_item', 'kind')):
    kol = [r[1] for r in s.execute('PRAGMA table_info(%s)' % t)]
    vr = next((k for k in ('updated_at', 'created_at', 'at', 'ts') if k in kol), None)
    for u in ('user1', 'user2', 'user3'):
        n = s.execute('SELECT COUNT(*) FROM %s WHERE username=?' % t, (u,)).fetchone()[0]
        posl = s.execute('SELECT MAX(%s) FROM %s WHERE username=?' % (vr, t), (u,)).fetchone()[0] if vr else ''
        po = dict(s.execute('SELECT %s, COUNT(*) FROM %s WHERE username=? GROUP BY 1' % (pole, t), (u,)).fetchall()) if pole else ''
        print('   %-16s %s: %d, последняя %s %s' % (t, u, n, posl, po))
# записи user3 по компаниям, которые теперь у другого: их статус в панели больше не виден (состояние – по паре инн+владелец)
n = s.execute("SELECT COUNT(*) FROM company_state st JOIN company_assignment a ON a.inn=st.inn "
              "WHERE st.username='user3' AND a.username<>'user3' AND COALESCE(st.call_result,'new')<>'new'").fetchone()[0]
print('статусов user3 (не «Новый») у компаний, которые теперь у user1/user2:', n)
kol = [r[1] for r in s.execute('PRAGMA table_info(activity_log)')]
vr = next((k for k in ('created_at', 'at', 'ts') if k in kol), None)
if vr:
    print('последние действия user3:', [tuple(r) for r in s.execute(
        "SELECT substr(%s,1,16), action FROM activity_log WHERE username='user3' ORDER BY %s DESC LIMIT 8" % (vr, vr))])
