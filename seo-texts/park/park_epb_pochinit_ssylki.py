# -*- coding: utf-8 -*-
"""Замена ссылок «номер ЭПБ, отправленный в поиск ЕИС» на карточку monitor-pb.

Меняем ТОЛЬКО те, где сервер открыл новую страницу и ИНН эксплуатанта на ней совпал
с ИНН факта (проверка park_1s_epb_perevod.py, 279 из 279 совпали). Старый адрес не
выбрасывается молча: он остаётся в поле `pochemu` рядом с новым, чтобы через месяц
было видно, откуда взялась замена.
"""
import json, os, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
c.execute("pragma table_info(fakt_ssylka)")
kol = [r[1] for r in c.fetchall()]
est_pochemu = 'pochemu' in kol

n = drugoy = ne_nashli = 0
for ln in open(os.path.join(D, 'park_epb_perevod.jsonl'), encoding='utf-8'):
    z = json.loads(ln)
    if z.get('verdikt') != 'ИНН совпал — ссылку меняем':
        drugoy += 1
        continue
    if est_pochemu:
        c.execute("update fakt_ssylka set url=?, pochemu=coalesce(pochemu,'')||"
                  "' [ссылка исправлена: номер ЭПБ вёл в поиск ЕИС, где его нет; "
                  "было '||?||']' where rowid=? and url=?",
                  (z['novaya'], z['staraya'], z['rowid'], z['staraya']))
    else:
        c.execute("update fakt_ssylka set url=? where rowid=? and url=?",
                  (z['novaya'], z['rowid'], z['staraya']))
    if c.rowcount:
        n += 1
    else:
        ne_nashli += 1
p.commit()
print('ссылок исправлено ......... %d' % n)
print('не тронуто (ИНН другой) ... %d' % drugoy)
print('строка не найдена ......... %d' % ne_nashli)
q = lambda s: c.execute(s).fetchone()[0]
print('осталось «номер ЭПБ в поиске ЕИС»: %d' %
      q(r"""select count(*) from fakt_ssylka s join fakt f on f.id=s.fakt_id
            where f.v_parke=1 and s.url like '%zakupki.gov.ru%searchString=%'
              and s.url glob '*searchString=[0-9][0-9]-*-[0-9]*-[0-9][0-9][0-9][0-9]'"""))
print('ссылок monitor-pb в парке: %d' %
      q("""select count(*) from fakt_ssylka s join fakt f on f.id=s.fakt_id
           where f.v_parke=1 and s.url like '%monitor-pb%'"""))
p.close()
