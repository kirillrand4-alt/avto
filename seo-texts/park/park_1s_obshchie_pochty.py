# -*- coding: utf-8 -*-
"""Помечает ОБЩИЕ почты организации, приписанные конкретному человеку.

Нашла 3-я сессия, проверяя ссылки ГЛАЗАМИ, а не счётчиком: её прибор сказал «контакт
доказан» — почта `info@myhistorypark.spb.ru` на странице есть. А на снимке оказалась страница
вакансий, и почта там общая почта организации, тогда как в строке она стояла рядом с именем
человека. Ссылка доказывает, что почта есть у организации, но не что она принадлежит этому
человеку.

Проверил у себя тем же признаком (префиксы info@, zakupki@, tender@ и подобные):

    строк «человек + почта» в выдаче   5 485
    из них общая почта организации       478

Не удаляю и не отвязываю: ставлю пометку `pochta_obshchaya=1`, чтобы в карточке было видно
«почта организации, принадлежность человеку не доказана». Правило владельца — разделять, а не
отсеивать; ровно так же поступили с посредниками и со сшитыми ИНН.
"""
import os, re, sqlite3, time

D = os.path.dirname(os.path.abspath(__file__))
OBSHCHAYA = re.compile(
    r'^(info|mail|e?mail|office|priemnaya|priem|reception|secretar|sekretar|kanc|kancel|'
    r'zakupki|zakupka|tender|torgi|hr|job|vacancy|sales|opt|shop|order|zakaz|market|'
    r'general|admin|director|post|adm|support|help|service|servis)[\d._-]*@', re.I)

p = sqlite3.connect(os.path.join(D, 'park.db'), timeout=120)
c = p.cursor()
if 'pochta_obshchaya' not in [r[1] for r in c.execute('pragma table_info(kontakt)')]:
    c.execute('alter table kontakt add column pochta_obshchaya integer default 0')
c.execute('update kontakt set pochta_obshchaya=0')

rows = c.execute("""select rowid, inn, znachenie, coalesce(person,'') from kontakt
                     where vid='email' and coalesce(person,'')<>''""").fetchall()
pometit = [r[0] for r in rows if OBSHCHAYA.match(r[2] or '')]
for i in range(0, len(pometit), 800):
    pack = pometit[i:i + 800]
    c.execute('update kontakt set pochta_obshchaya=1 where rowid in (%s)'
              % ','.join('?' * len(pack)), pack)
c.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
          (time.strftime('%Y-%m-%d %H:%M:%S'), 'ПОЧТА: общая почта организации на человеке',
           len(rows), len(pometit), len(rows) - len(pometit),
           'префиксы info@/zakupki@/tender@ и подобные; принадлежность человеку не доказана'))
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
V = """inn in (select distinct inn from fakt where v_parke=1 and coalesce(v_obzvone,0)=0
               and coalesce(posrednik,0)=0)"""
print('строк «человек + почта» всего ......... %d' % len(rows))
print('  помечено общей почтой организации ... %d' % len(pometit))
print('в выдаче: строк «человек + почта» %d, из них общих %d'
      % (q("select count(*) from kontakt where vid='email' and coalesce(person,'')<>'' and " + V),
         q("select count(*) from kontakt where vid='email' and pochta_obshchaya=1 and " + V)))
print('предприятий, где ЕДИНСТВЕННАЯ почта человека — общая: %d'
      % q("""select count(*) from (
               select inn from kontakt where vid='email' and coalesce(person,'')<>'' and """ + V + """
                group by inn having sum(case when coalesce(pochta_obshchaya,0)=0 then 1 else 0 end)=0)"""))
p.close()
